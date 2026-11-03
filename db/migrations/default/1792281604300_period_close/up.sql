-- Copyright 2026 Signet Team
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--
-- SPDX-License-Identifier: Apache-2.0

-- Chốt kỳ số liệu điều hành (#542): lãnh đạo đơn vị chốt một tháng đã qua, số của bốn khung nhìn dashboard
-- (migration 1792281601200) được chép một lần vào office.period_closes, không sửa, không xóa được. Mã băm sha256 của
-- bản chép vào sổ kiểm toán (sự kiện period.closed), sổ có chuỗi băm và mốc neo nên `make audit` phát hiện được
-- bản chép bị sửa sau đó.
--
-- v_document_counts, v_overdue_by_department là số tại lúc xem, không có lịch sử: bản chép giữ số tại lúc chốt
-- (closed_at), không phải số cuối tháng. v_processing_time, v_outgoing_by_month theo tháng: lấy đúng dòng của kỳ.
-- Băm đúng chuỗi figures::text (jsonb in khóa theo thứ tự cố định), nên tính lại được bằng
--   select encode(sha256(convert_to(figures::text, 'UTF8')), 'hex') from office.period_closes …

create table office.period_closes (
  tenant_id  uuid not null references core.tenants,
  period     date not null check (period = date_trunc('month', period)::date),   -- ngày 1 của tháng
  closed_at  timestamptz not null default now(),
  closed_by  text not null,
  figures    jsonb not null,
  sha256     bytea not null check (octet_length(sha256) = 32),
  primary key (tenant_id, period)
);

create function office.period_closes_frozen() returns trigger
language plpgsql
as $$
begin
  raise exception 'kỳ đã chốt không sửa, không xóa được' using errcode = 'insufficient_privilege';
end
$$;

create trigger period_closes_frozen before update or delete on office.period_closes
  for each row execute function office.period_closes_frozen();
create trigger period_closes_no_truncate before truncate on office.period_closes
  for each statement execute function office.period_closes_frozen();

create function office.close_period(period date, hasura_session json)
returns setof office.period_closes
language plpgsql volatile set search_path = pg_catalog, pg_temp
as $$
declare
  tenant  uuid := (hasura_session ->> 'x-hasura-tenant-id')::uuid;
  ky      date := date_trunc('month', close_period.period)::date;
  figures jsonb;
  digest  bytea;
begin
  if coalesce(hasura_session ->> 'x-hasura-role', '') <> 'director' or tenant is null then
    raise exception 'chỉ lãnh đạo đơn vị chốt kỳ' using errcode = 'insufficient_privilege';
  end if;
  if ky >= date_trunc('month', now() at time zone 'Asia/Ho_Chi_Minh')::date then
    raise exception 'kỳ % chưa kết thúc', to_char(ky, 'MM/YYYY') using errcode = 'check_violation';
  end if;

  figures := jsonb_build_object(
    'period', ky,
    'counts', (select coalesce(jsonb_agg(to_jsonb(c) - 'tenant_id'
                                         order by c.direction, c.restricted, c.status, c.urgency, c.overdue), '[]')
                 from office.v_document_counts c where c.tenant_id = tenant),
    'departments', (select coalesce(jsonb_agg(to_jsonb(d) - 'tenant_id' order by d.code nulls last), '[]')
                      from office.v_overdue_by_department d where d.tenant_id = tenant),
    'processing', (select to_jsonb(p) - 'tenant_id' - 'month'
                     from office.v_processing_time p where p.tenant_id = tenant and p.month = ky),
    'outgoing', (select to_jsonb(o) - 'tenant_id' - 'month'
                   from office.v_outgoing_by_month o where o.tenant_id = tenant and o.month = ky));
  digest := sha256(convert_to(figures::text, 'UTF8'));

  insert into office.period_closes (tenant_id, period, closed_by, figures, sha256)
  values (tenant, ky, hasura_session ->> 'x-hasura-user-id', figures, digest)
  on conflict on constraint period_closes_pkey do nothing;
  if not found then
    raise exception 'kỳ % đã chốt', to_char(ky, 'MM/YYYY') using errcode = 'unique_violation';
  end if;

  insert into core.audit_log (tenant_id, actor_id, actor_kind, request_id, action, entity, entity_id, diff)
  values (tenant, hasura_session ->> 'x-hasura-user-id', 'user',
          coalesce(hasura_session ->> 'x-hasura-request-id', nullif(current_setting('moc.request_id', true), '')),
          'period.closed', 'office.period_closes', tenant || '/' || ky,
          jsonb_build_object('period', ky, 'sha256', encode(digest, 'hex')));
  return query select * from office.period_closes pc where pc.tenant_id = tenant and pc.period = ky;
end
$$;

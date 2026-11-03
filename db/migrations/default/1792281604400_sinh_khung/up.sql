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

-- Khung (harness) cho ứng dụng sinh từ Supabase Studio (#562). Bảng tạo trong schema sinh (qua Studio,
-- postgres-meta bằng vai trò moc_studio) tự có:
--   tenant_id, created_by, created_at do trigger đặt từ token (người gọi không ghi được);
--   RLS ENABLE (không FORCE: chủ bảng moc_studio là người vận hành, được tin, vượt RLS), policy đơn vị
--   AS RESTRICTIVE TO PUBLIC (mọi vai trò khác chủ bảng, kể cả vai trò thêm sau, bị khóa trong đơn vị);
--   sổ kiểm toán chuỗi băm core.audit(), chặn TRUNCATE; mỗi lệnh DDL cũng ghi sổ.
-- Lệnh gỡ một trong các thứ đó thì bị hủy (RAISE), không tự khôi phục ngầm.
-- Hasura nối bằng superuser nên vượt RLS: policy chỉ bảo vệ đường /rest/v1 (PostgREST). Không track bảng sinh.

-- Vai trò (thuộc cả máy chủ PostgreSQL; `moc backup restore` tạo lại bằng đúng đoạn này, xem SINH_ROLES_SQL ở
-- scripts/ung_dung.py). Tạo NOLOGIN; dịch vụ khởi động bật LOGIN, đặt mật khẩu cho authenticator và moc_studio.
-- authenticator: PostgREST nối bằng vai trò này rồi đổi sang vai trò người dùng theo claim x-hasura-default-role.
-- Năm vai trò người dùng trùng moc_role của realm. Không có vai trò ẩn danh: yêu cầu không token bị 401.
-- moc_studio: Studio, postgres-meta nối bằng vai trò này; chủ schema sinh, không thấy core. Không bao giờ cấp cho
-- authenticator. moc_harness: chủ các hàm SECURITY DEFINER của khung, không phải superuser.
do $moc$ begin
  if not exists (select 1 from pg_roles where rolname = 'authenticator') then
    create role authenticator nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'staff') then create role staff nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'clerk') then create role clerk nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'manager') then create role manager nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'director') then create role director nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'tenant_admin') then create role tenant_admin nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'moc_studio') then create role moc_studio nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'moc_harness') then create role moc_harness nologin; end if;
end $moc$;
grant staff, clerk, manager, director, tenant_admin to authenticator;
grant moc_studio to moc_harness;

create schema sinh authorization moc_studio;
grant usage on schema sinh to staff, clerk, manager, director, tenant_admin;
grant usage on schema core to moc_harness;
grant execute on function core.audit() to moc_harness;
grant references on core.tenants to moc_harness;
grant insert on core.audit_log to moc_harness;

create schema sinh_khung;                    -- hàm của khung; PostgREST không mở schema này
grant usage on schema sinh_khung to public;

-- Ứng dụng cài bằng `moc app` không được lấy hai schema này
alter table core.apps drop constraint apps_schema_name_check,
  add constraint apps_schema_name_check check (schema_name ~ '^[a-z][a-z0-9_]*$' and char_length(schema_name) <= 50
                                               and schema_name not in ('core', 'office', 'personal', 'public',
                                                                       'moc_app', 'sinh', 'sinh_khung'));

-- Claim trong namespace của Hasura: cùng token Keycloak, cùng nguồn sự thật với quyền Hasura
create function sinh_khung.claim(k text) returns text
language sql stable set search_path = pg_catalog, pg_temp
as $$ select nullif(current_setting('request.jwt.claims', true), '')::jsonb -> 'https://hasura.io/jwt/claims' ->> k $$;

-- PostgREST gọi trước mỗi yêu cầu: core.audit() ghi người làm từ moc.actor (đường "ghi thẳng CSDL" của core.audit)
create function sinh_khung.truoc_yeu_cau() returns void
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare c jsonb := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
begin
  perform set_config('moc.actor',
                     coalesce(c -> 'https://hasura.io/jwt/claims' ->> 'x-hasura-user-id', c ->> 'sub', '?'), true);
  perform set_config('moc.actor_kind', 'user', true);
  perform set_config('moc.request_id',
                     coalesce(nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-request-id', ''),
                     true);
end
$$;

-- Cột chuẩn: người gọi gửi gì cũng bị thay bằng giá trị từ token; sửa dòng thì giữ nguyên giá trị cũ.
-- Áp cho mọi cột thêm sau mà không phải cấp lại quyền từng cột.
create function sinh_khung.cot_chuan() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  if tg_op = 'INSERT' then
    new.tenant_id := coalesce(sinh_khung.claim('x-hasura-tenant-id')::uuid, new.tenant_id);
    new.created_by := coalesce(sinh_khung.claim('x-hasura-user-id'), new.created_by);
    new.created_at := now();
  else
    new.tenant_id := old.tenant_id;
    new.created_by := old.created_by;
    new.created_at := old.created_at;
  end if;
  return new;
end
$$;

create function sinh_khung.chan_xoa_het() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  raise exception 'khung: không TRUNCATE bảng %: xóa dữ liệu mọi đơn vị mà không ghi sổ', tg_table_name;
end
$$;

-- Ghi một dòng sổ cho lệnh DDL: ai (vai trò đăng nhập), lệnh gì, trên đối tượng nào
create function sinh_khung.ghi_ddl(lenh text, doi_tuong text) returns void
language plpgsql security definer set search_path = pg_catalog, pg_temp
as $$
begin
  insert into core.audit_log (tenant_id, actor_id, actor_kind, request_id, action, entity, entity_id, diff)
  values (null, session_user::text, 'user', null, 'ddl', 'sinh', doi_tuong, jsonb_build_object('lenh', lenh));
end
$$;
alter function sinh_khung.ghi_ddl(text, text) owner to moc_harness;
revoke all on function sinh_khung.ghi_ddl(text, text) from public;
grant execute on function sinh_khung.ghi_ddl(text, text) to moc_studio;

-- Gắn khung vào một bảng. Chạy lại bao nhiêu lần cũng cho cùng kết quả.
create function sinh_khung.ap_khung(bang oid) returns void
language plpgsql security definer set search_path = pg_catalog, pg_temp
as $$
declare s text; n text; q text;
begin
  select ns.nspname, c.relname into s, n
    from pg_class c join pg_namespace ns on ns.oid = c.relnamespace
   where c.oid = bang and c.relkind in ('r', 'p');
  if s is distinct from 'sinh' then return; end if;
  q := format('%I.%I', s, n);
  if not exists (select 1 from pg_attribute where attrelid = bang and attname = 'tenant_id' and not attisdropped) then
    execute format('alter table %s add column tenant_id uuid not null references core.tenants', q);
  end if;
  if not exists (select 1 from pg_attribute where attrelid = bang and attname = 'created_by' and not attisdropped) then
    execute format('alter table %s add column created_by text', q);
  end if;
  if not exists (select 1 from pg_attribute where attrelid = bang and attname = 'created_at' and not attisdropped) then
    execute format('alter table %s add column created_at timestamptz not null default now()', q);
  end if;
  execute format('alter table %s enable row level security', q);
  if not exists (select 1 from pg_policy where polrelid = bang and polname = 'moc_don_vi') then
    execute format('create policy moc_don_vi on %s as restrictive for all to public '
                   'using (tenant_id = (select sinh_khung.claim(%L))::uuid) '
                   'with check (tenant_id = (select sinh_khung.claim(%L))::uuid)',
                   q, 'x-hasura-tenant-id', 'x-hasura-tenant-id');
  end if;
  if not exists (select 1 from pg_policy where polrelid = bang and polname = 'moc_mo') then
    execute format('create policy moc_mo on %s as permissive for all to public '
                   'using (true) with check (true)', q);
  end if;
  execute format('grant select, insert, update, delete on %s to staff, clerk, manager, director, tenant_admin', q);
  execute 'grant usage, select on all sequences in schema sinh to staff, clerk, manager, director, tenant_admin';
  if not exists (select 1 from pg_trigger where tgrelid = bang and tgname = 'moc_cot_chuan') then
    execute format('create trigger moc_cot_chuan before insert or update on %s '
                   'for each row execute function sinh_khung.cot_chuan()', q);
  end if;
  if not exists (select 1 from pg_trigger where tgrelid = bang and tgname = 'moc_so') then
    execute format('create trigger moc_so after insert or update or delete on %s '
                   'for each row execute function core.audit()', q);
  end if;
  if not exists (select 1 from pg_trigger where tgrelid = bang and tgname = 'moc_khong_xoa_het') then
    execute format('create trigger moc_khong_xoa_het before truncate on %s '
                   'for each statement execute function sinh_khung.chan_xoa_het()', q);
  end if;
end
$$;
alter function sinh_khung.ap_khung(oid) owner to moc_harness;
revoke all on function sinh_khung.ap_khung(oid) from public;
grant execute on function sinh_khung.ap_khung(oid) to moc_studio;

-- Bất biến của một bảng trong sinh; sai thì hủy cả lệnh
create function sinh_khung.kiem_bang(bang oid) returns void
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare r record; t text;
begin
  select c.relname, c.relrowsecurity, c.relowner::regrole::text as chu into r
    from pg_class c where c.oid = bang and c.relkind in ('r', 'p');
  if not found then return; end if;
  if r.chu <> 'moc_studio' then
    raise exception 'khung: bảng % phải thuộc moc_studio', r.relname;
  end if;
  if not r.relrowsecurity then
    raise exception 'khung: bảng % phải giữ ENABLE ROW LEVEL SECURITY', r.relname;
  end if;
  if not exists (select 1 from pg_policy where polrelid = bang and polname = 'moc_don_vi' and not polpermissive
                   and polcmd = '*' and polroles = array[0]::oid[]) then
    raise exception 'khung: bảng % thiếu policy đơn vị moc_don_vi (restrictive, mọi lệnh, to public)', r.relname;
  end if;
  foreach t in array array['moc_cot_chuan', 'moc_so', 'moc_khong_xoa_het'] loop
    if not exists (select 1 from pg_trigger where tgrelid = bang and tgname = t and tgenabled in ('O', 'A')) then
      raise exception 'khung: bảng % phải bật trigger %', r.relname, t;
    end if;
  end loop;
  foreach t in array array['tenant_id', 'created_by', 'created_at'] loop      -- cot_chuan ghi cả ba cột
    if not exists (select 1 from pg_attribute where attrelid = bang and attname = t and not attisdropped) then
      raise exception 'khung: bảng % thiếu cột chuẩn %', r.relname, t;
    end if;
  end loop;
end
$$;

-- Sau mỗi lệnh DDL. Hàm chạy bằng quyền người gõ lệnh: lệnh của superuser (migration lõi) và của moc_harness (chính
-- ap_khung) bỏ qua, nên ALTER TABLE do ap_khung chạy không gọi lại khung.
create function sinh_khung.gac() returns event_trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare r record; s text; bang oid; ten text; doi boolean := false;
begin
  if current_user = 'moc_harness' or (select rolsuper from pg_roles where rolname = current_user) then return; end if;
  for r in select * from pg_event_trigger_ddl_commands() loop
    s := r.schema_name; bang := null; ten := null;
    if r.object_type in ('table', 'table column') then bang := r.objid; end if;   -- RENAME COLUMN là 'table column'
    if r.object_type = 'policy' then              -- policy, trigger, rule không thuộc schema: lấy schema của bảng
      select c.oid, ns.nspname, p.polname into bang, s, ten from pg_policy p join pg_class c on c.oid = p.polrelid
        join pg_namespace ns on ns.oid = c.relnamespace where p.oid = r.objid;
    elsif r.object_type = 'trigger' then
      select c.oid, ns.nspname, t.tgname into bang, s, ten from pg_trigger t join pg_class c on c.oid = t.tgrelid
        join pg_namespace ns on ns.oid = c.relnamespace where t.oid = r.objid;
    elsif r.object_type = 'rule' then
      select c.oid, ns.nspname into bang, s from pg_rewrite w join pg_class c on c.oid = w.ev_class
        join pg_namespace ns on ns.oid = c.relnamespace where w.oid = r.objid;
    end if;
    if s is distinct from 'sinh' then continue; end if;
    doi := true;
    -- view, hàm chạy bằng quyền chủ bảng (vượt RLS) hoặc lộ ra /rest/v1/rpc: không cho tạo trong sinh
    if r.command_tag in ('CREATE RULE', 'CREATE VIEW', 'CREATE MATERIALIZED VIEW', 'CREATE FUNCTION',
                         'CREATE PROCEDURE', 'ALTER FUNCTION', 'ALTER PROCEDURE', 'CREATE AGGREGATE') then
      raise exception 'khung: không % trong schema sinh', r.command_tag;
    end if;
    if r.command_tag = 'ALTER POLICY' and ten in ('moc_don_vi', 'moc_mo') then
      raise exception 'khung: policy % do khung quản lý', ten;
    end if;
    perform sinh_khung.ghi_ddl(r.command_tag, r.object_identity);
    if r.object_type = 'table' and r.command_tag in ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO') then
      perform sinh_khung.ap_khung(bang);
    end if;
    if bang is not null then perform sinh_khung.kiem_bang(bang); end if;
  end loop;
  if doi then perform pg_notify('pgrst', 'reload schema'); end if;   -- PostgREST thấy bảng, cột mới ngay
end
$$;
create event trigger moc_gac on ddl_command_end execute function sinh_khung.gac();

-- Bảng do superuser tạo trong sinh (gac bỏ qua superuser) không có khung: gọi hàm này ở cuối seed và trong test,
-- thiếu ở bảng nào thì hủy. Seed bằng superuser vẫn đúng nếu `set role moc_studio` trước khi tạo bảng.
create function sinh_khung.kiem_tat_ca() returns void
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare b oid;
begin
  for b in select c.oid from pg_class c join pg_namespace ns on ns.oid = c.relnamespace
            where ns.nspname = 'sinh' and c.relkind in ('r', 'p') loop
    perform sinh_khung.kiem_bang(b);
  end loop;
end
$$;

-- Sau mỗi lệnh xóa: pg_event_trigger_ddl_commands() không trả lệnh DROP nên gac không thấy. Xóa policy đơn vị,
-- trigger hay cột chuẩn của khung (kể cả qua CASCADE) mà bảng còn, hay xóa cả schema sinh: hủy lệnh. Xóa khác trong
-- sinh thì cho, ghi sổ và báo PostgREST (bảng đã xóa rời menu /rest/v1/ ngay).
create function sinh_khung.gac_xoa() returns event_trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare r record; doi boolean := false;
begin
  if current_user = 'moc_harness' or (select rolsuper from pg_roles where rolname = current_user) then return; end if;
  for r in select * from pg_event_trigger_dropped_objects() loop
    if r.object_type = 'schema' and r.object_identity = 'sinh' then
      raise exception 'khung: không xóa schema sinh';
    end if;
    -- policy, trigger không có schema_name; address_names = {schema, bảng, tên}
    if coalesce(r.schema_name, r.address_names[1]) is distinct from 'sinh' then continue; end if;
    if r.object_type in ('policy', 'trigger', 'table column')
       and r.address_names[3] in ('moc_don_vi', 'moc_cot_chuan', 'moc_so', 'moc_khong_xoa_het',
                                  'tenant_id', 'created_by', 'created_at')
       and to_regclass(format('%I.%I', r.address_names[1], r.address_names[2])) is not null then
      raise exception 'khung: không xóa % (%) của khung', r.object_type, r.object_identity;
    end if;
    if r.original then
      perform sinh_khung.ghi_ddl(tg_tag, r.object_identity);
      doi := true;
    end if;
  end loop;
  if doi then perform pg_notify('pgrst', 'reload schema'); end if;
end
$$;
create event trigger moc_gac_xoa on sql_drop execute function sinh_khung.gac_xoa();

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

-- Ngược của up.sql: bảng của ứng dụng sinh mất theo schema sinh. Dòng sổ kiểm toán giữ nguyên (sổ chỉ ghi thêm).

drop event trigger moc_gac_xoa;
drop event trigger moc_gac;
drop schema sinh cascade;
drop schema sinh_khung cascade;
alter table core.apps drop constraint apps_schema_name_check,
  add constraint apps_schema_name_check check (schema_name ~ '^[a-z][a-z0-9_]*$' and char_length(schema_name) <= 50
                                               and schema_name not in ('core', 'office', 'personal', 'public',
                                                                       'moc_app'));
revoke insert on core.audit_log from moc_harness;
revoke references on core.tenants from moc_harness;
revoke execute on function core.audit() from moc_harness;
revoke usage on schema core from moc_harness;
drop role moc_harness, moc_studio, authenticator, staff, clerk, manager, director, tenant_admin;

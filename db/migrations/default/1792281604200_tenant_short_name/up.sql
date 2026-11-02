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

-- #466: tên ngắn của đơn vị cho chỗ hẹp (thanh trên, thẻ); NULL là dùng `name`. Giao diện hiện `short_name ?? name`,
-- tên đầy đủ khi rê chuột, không tự cắt chuỗi.
--
-- Hai đơn vị mẫu (seed/tenants.sql, id cố định) đổi tên: Khoa Công nghệ thông tin → Trường Công nghệ thông tin và
-- Truyền thông (tên ngắn Trường CNTT & TT), Khoa Kinh tế → Trường Kinh tế, người đứng đầu ký là Hiệu trưởng. Chỉ đổi
-- khi đúng id mẫu VÀ còn giá trị cũ: đơn vị thật (id khác) và đơn vị đã đổi tay (bản online 01/11) giữ nguyên; chạy
-- lại không đổi gì. Trigger audit ghi mỗi dòng đổi vào sổ kiểm toán (người thực hiện: migration).

alter table core.tenants
  add column short_name text check (short_name is null or btrim(short_name) <> '');

set local moc.actor = 'migration:1792281604200_tenant_short_name';
set local moc.actor_kind = 'system';

update core.tenants set name = 'Trường Công nghệ thông tin và Truyền thông'
 where id = 'c300d5bb-028f-44cc-ba10-7b5277a4225d' and name = 'Khoa Công nghệ thông tin';
update core.tenants set name = 'Trường Kinh tế'
 where id = '318da474-60d6-4a90-aa7f-928b31b8fc59' and name = 'Khoa Kinh tế';
update core.tenants set head_title = 'Hiệu trưởng'
 where id in ('c300d5bb-028f-44cc-ba10-7b5277a4225d', '318da474-60d6-4a90-aa7f-928b31b8fc59')
   and head_title = 'Trưởng khoa';
update core.tenants set short_name = 'Trường CNTT & TT'
 where id = 'c300d5bb-028f-44cc-ba10-7b5277a4225d' and name = 'Trường Công nghệ thông tin và Truyền thông'
   and short_name is null;

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

-- Ngược của up.sql: trả tên cũ cho hai đơn vị mẫu (chỉ khi còn đúng tên mới), bỏ cột short_name.

set local moc.actor = 'migration:1792281604200_tenant_short_name:down';
set local moc.actor_kind = 'system';

update core.tenants set name = 'Khoa Công nghệ thông tin'
 where id = 'c300d5bb-028f-44cc-ba10-7b5277a4225d' and name = 'Trường Công nghệ thông tin và Truyền thông';
update core.tenants set name = 'Khoa Kinh tế'
 where id = '318da474-60d6-4a90-aa7f-928b31b8fc59' and name = 'Trường Kinh tế';
update core.tenants set head_title = 'Trưởng khoa'
 where id in ('c300d5bb-028f-44cc-ba10-7b5277a4225d', '318da474-60d6-4a90-aa7f-928b31b8fc59')
   and head_title = 'Hiệu trưởng';

alter table core.tenants drop column short_name;

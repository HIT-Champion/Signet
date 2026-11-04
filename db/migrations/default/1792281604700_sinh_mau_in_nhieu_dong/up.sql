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

-- Mẫu in nhiều dòng trên /sinh (#601). Cột text không có maxLength trong OpenAPI của PostgREST, nên biểu mẫu chung
-- (apps/sinh/public/schema-form.js: ô nhiều dòng chỉ khi maxLength > 200) hiện ô một dòng và gộp mọi xuống dòng
-- thành dấu cách: sửa mẫu là mất đoạn, tiêu đề. varchar(20000) cho PostgREST ghi maxLength 20000 và giữ giới hạn độ
-- dài, nên CHECK cũ thừa. Chạy bằng moc_studio như lúc tạo bảng, để khung ghi sổ và kiểm lại bảng.
set role moc_studio;
alter table sinh.mau_in drop constraint mau_in_noi_dung,
  alter column noi_dung type varchar(20000);
reset role;
select sinh_khung.kiem_tat_ca();

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

-- Ngược của up.sql: về text với CHECK 20 000 ký tự như 1792281604600.
set role moc_studio;
alter table sinh.mau_in alter column noi_dung type text,
  add constraint mau_in_noi_dung check (char_length(noi_dung) <= 20000);
reset role;
select sinh_khung.kiem_tat_ca();

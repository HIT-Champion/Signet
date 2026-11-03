#!/bin/sh
# Copyright 2026 Signet Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

# rest-init (#566): chạy một lần mỗi lần `docker compose up`, trước PostgREST và Studio.
# 1. Bật LOGIN, đặt mật khẩu cho authenticator (PostgREST) và moc_studio (Studio, postgres-meta). Migration
#    1792281604400_sinh_khung tạo hai vai trò này NOLOGIN; mật khẩu nằm trong .env, không nằm trong migration.
# 2. Lấy khóa công khai của realm, ghi JWKS cho PostgREST đọc bằng PGRST_JWT_SECRET=@tệp: PostgREST không tự tải
#    jwk_url như Hasura. Chỉ giữ khóa ký (use = sig), bỏ khóa mã hóa. Keycloak đổi khóa giữa chừng thì chạy lại:
#    docker compose up -d rest-init rest
set -eu
export PGPASSWORD="$POSTGRES_PASSWORD"
q() { psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -At -v ON_ERROR_STOP=1 "$@"; }

q -v rest="$MOC_REST_DB_PASSWORD" -v studio="$MOC_STUDIO_DB_PASSWORD" <<'SQL'
alter role authenticator with login password :'rest';
alter role moc_studio with login password :'studio';
SQL

certs=$(wget -qO- "http://keycloak:8080/realms/$MOC_REALM/protocol/openid-connect/certs")
q -v certs="$certs" > /run/jwks/jwks.json.moi <<'SQL'
select jsonb_build_object('keys', coalesce(jsonb_agg(k), '[]'::jsonb))
  from jsonb_array_elements((:'certs')::jsonb -> 'keys') k where k ->> 'use' = 'sig';
SQL
grep -q '"kty"' /run/jwks/jwks.json.moi || { echo "rest-init: realm $MOC_REALM không có khóa ký nào" >&2; exit 1; }
chmod 644 /run/jwks/jwks.json.moi
mv /run/jwks/jwks.json.moi /run/jwks/jwks.json
echo "rest-init: đã đặt mật khẩu vai trò, JWKS có $(grep -o '"kid"' /run/jwks/jwks.json | wc -l) khóa ký"

# app-sinh — Ứng dụng sinh từ bảng

Trang chung cho mọi bảng người vận hành nền tảng tạo trong Studio ở schema `sinh` (#560). Cắm vào lõi bằng một lệnh
như các ứng dụng khác:

```bash
python3 scripts/moc.py app install apps/sinh/app.yaml      # make app-install APP=apps/sinh/app.yaml
python3 scripts/moc.py app remove sinh                     # gỡ: trang, client, container; bảng trong schema sinh còn
```

Không có mã riêng cho bảng nào. Trang đọc mô tả API mà PostgREST tự sinh (`GET /rest/v1/`, Swagger 2.0) rồi dựng:

- **menu**: mỗi bảng có `COMMENT ON TABLE` là một mục. Dòng đầu chú thích là tên, các dòng sau là lời giới thiệu.
  Bảng không chú thích là bảng phụ, không lên menu;
- **biểu mẫu thêm, sửa**: dựng bằng `schema-form.js` (chép từ `apps/nghi-phep`) từ JSON Schema do `openapi.js` đổi ra.
  Nhãn ô là dòng đầu `COMMENT ON COLUMN`, các dòng sau là gợi ý dưới ô;
- **danh sách**: 50 dòng mới nhất theo `created_at`, kèm tổng số dòng;
- **báo cáo** (#587): mỗi dòng của bảng `sinh.bao_cao` (menu **Báo cáo**) là một báo cáo: bảng nguồn, cột nhóm, phép
  tính, cột số, kiểu hiện. Nút **Xem báo cáo** ở mỗi dòng mở báo cáo ngay trong thẻ. `bao-cao.js` kiểm khai báo theo mô
  tả API (cột nhóm là enum, `date` hay `timestamptz`; cột số có kiểu số; tên cột chỉ chữ thường, số, `_` vì luật WAF
  10093), dựng truy vấn hàm gộp
  (`select=<nhóm>,count()`, `<cột>.sum()`, `<cột>.avg()`), xếp nhóm enum theo thứ tự enum (thiếu thì 0), cộng nhóm ngày
  theo tháng giờ Việt Nam. Luôn có bảng số; biểu đồ cột là thanh CSS, tròn là `conic-gradient` tám màu (nhóm thứ chín
  trở đi vào "Khác"), đặt kiểu qua `el.style` vì CSP chặn thuộc tính `style=`; không thư viện biểu đồ. Quá 5 giây
  (`statement_timeout`, PostgREST trả `500` mã `57014`) thì báo một câu riêng;
- **nút In** (#586): bảng có mẫu trong `sinh.mau_in` (`GET /rest/v1/mau_in?bang=eq.<bảng>&select=id,ten`) thì mỗi dòng
  có nút **In** cạnh Sửa; nhiều mẫu thì chọn ở ô **Mẫu in**. Bấm In thì gọi `GET /api/sinh/<bảng>/<id>/pdf?mau=<id>`
  của svc-files kèm token, kiểm là `application/pdf`, tải về `<bảng>-<id>.pdf`. Không có mẫu, bản cài chưa có
  `mau_in`, hay khóa chính không phải cột `id` số nguyên dương thì không có nút. Cú pháp mẫu:
  [`docs/them-ung-dung.md`](../../docs/them-ung-dung.md) mục 8.7.

Thêm cột trong Studio thì lần quay lại tab này trang nạp lại mô tả, ô mới hiện ngay, chữ đang gõ vẫn giữ. Bảng, cột,
quyền nằm trong CSDL: khung CSDL của lõi gắn cách ly đơn vị (RLS), sổ kiểm toán và cột chuẩn cho mọi bảng của schema
`sinh`, PostgREST đặt vai trò, đơn vị theo token. Trang chỉ gửi token của người dùng.

## Cột thành ô nhập

| Cột PostgreSQL | Ô |
|---|---|
| `text`, `varchar(n)` | ô một dòng (`varchar(n)`: tối đa n ký tự) |
| kiểu enum | ô chọn (giá trị enum là chữ hiện ra) |
| `integer`, `bigint`, `numeric`… | ô số |
| `boolean` | ô đánh dấu |
| `date` | ô ngày |
| `uuid` | ô một dòng, kiểm dạng UUID |
| `json`, `jsonb`, mảng | không có ô (biểu mẫu chưa sửa được kiểu này) |
| `tenant_id`, `created_by`, `created_at`, khóa chính một cột | không có ô: khung CSDL điền, người gọi không ghi được |
| khóa chính nhiều cột | có ô (người dùng nhập); dòng không có nút Sửa |

- `NOT NULL` không có giá trị mặc định là ô bắt buộc.
- Cột có giá trị mặc định thì để trống được, CSDL tự điền.
- Cột cho phép NULL, để trống thì gửi `null`. Riêng ô chọn để trống thì không gửi, nên lúc sửa không xóa về trống
  được.
- `CHECK` không hiện thành ô chọn, vì PostgREST không mô tả nó. Muốn có danh sách chọn thì dùng kiểu enum.
- Studio đặt sẵn kiểu `text` cho mọi cột chữ, nên `text` không nói gì về độ dài: mọi cột chữ là ô một dòng.

## Tệp

| Tệp | Nội dung |
|---|---|
| `app.yaml` | Manifest: đường `/sinh`, image dựng từ thư mục này, 64 MiB. `database` chỉ vì manifest bắt buộc: schema trống `trang_sinh`, không migration. Bảng của các ứng dụng sinh ở schema `sinh`, do khung CSDL của lõi làm chủ |
| `public/openapi.js` | Mô tả API → menu, JSON Schema cho `schema-form.js`. Hàm thuần |
| `public/bao-cao.js` | Khai báo báo cáo → kiểm theo mô tả API, đường truy vấn hàm gộp, số liệu cho bảng và biểu đồ (cộng theo tháng, màu biểu đồ tròn). Hàm thuần |
| `public/rest.js` | Đường `/rest/v1`, đường in của svc-files (`duongIn`), tham số fetch (`Prefer: return=representation`, `count=exact` cho danh sách), đọc trả lời theo mã HTTP. 403 không kèm JSON là WAF ở cổng chặn, không phải thiếu quyền |
| `public/app.js` | Vẽ menu, biểu mẫu, danh sách; nạp lại mô tả khi quay lại tab (`visibilitychange`) |
| `public/auth.js`, `server.py`, `Dockerfile`, `public/style.css` | Như `apps/nghi-phep`: trang tĩnh Python thư viện chuẩn, không root; đăng nhập PKCE bằng client `app-sinh` |
| `public/i18n.js` | Bảng dịch vi/en của trang. Tên bảng, nhãn ô lấy từ COMMENT trong CSDL nên chỉ một thứ tiếng |
| `tests/` | `node --test tests/*.test.js`: bộ đổi mô tả API (cả màn "thêm cột Mức ưu tiên"), cách gọi `/rest/v1`, bảng dịch, báo cáo (`bao-cao.test.js`: khai báo, truy vấn, cộng theo tháng; giá trị enum khớp migration), đường in và khi nào có nút In (`in.test.js`). `python3 -m unittest discover -s tests`: máy chủ trang thật trên cổng ngẫu nhiên |

`tests/postgrest-v14-openapi.json` là mô tả thật của PostgREST v14.18 lấy từ bộ thử trên CI (bảng mẫu `sinh.yeu_cau`).
`tests/postgrest-openapi.json` viết tay theo đúng dạng đó cho các ca bản thật chưa có: khóa ngoại, json, mảng, bảng
không chú thích, chú thích nhiều dòng.

## Chưa làm

- Xóa dòng, phân trang (chỉ 50 dòng mới nhất), lọc, tìm.
- Ô cho cột thời điểm (`timestamp`): hiện ô chữ, gõ theo dạng ISO 8601.
- Ô nhiều dòng cho cột chữ dài.
- Nhãn hai thứ tiếng: COMMENT chỉ một chuỗi.
- Báo cáo: lọc theo khoảng ngày hay giá trị, điền tháng trống, xuất tệp; nhiều cột nhóm.
- In: mở PDF ở tab mới (trình chặn cửa sổ bật lên chặn sau `await`), xem trước mẫu trên trang.

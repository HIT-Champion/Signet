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
  Ô theo kiểu cột, nhãn theo chú thích: xem hai mục dưới;
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
| `text` | ô nhiều dòng |
| `varchar(n)` | ô một dòng, tối đa n ký tự |
| kiểu enum | ô chọn (giá trị enum là chữ hiện ra) |
| `integer`, `bigint`, `numeric`… | ô số |
| `boolean` | ô đánh dấu |
| `date` | ô ngày |
| `timestamp`, `timestamptz` | ô ngày giờ (`datetime-local`) theo giờ của máy; gửi kèm độ lệch múi giờ, nên `timestamptz` lưu đúng thời điểm, `timestamp` lưu đúng giờ đã gõ |
| `uuid` | ô một dòng, kiểm dạng UUID |
| `json`, `jsonb` | ô nhiều dòng; gõ chưa đúng cú pháp JSON thì báo dưới ô, không gửi |
| mảng của kiểu enum (`trang_thai[]`) | nhiều ô đánh dấu, một ô mỗi giá trị enum |
| mảng khác (`text[]`, `integer[]`…) | ô chỉ đọc: hiện giá trị, không bắt buộc, không gửi đi |
| `tenant_id`, `created_by`, `created_at`, khóa chính một cột | không có ô: khung CSDL điền, người gọi không ghi được |
| khóa chính nhiều cột | có ô (người dùng nhập); dòng không có nút Sửa |

- `NOT NULL` không có giá trị mặc định là ô bắt buộc.
- Cột có giá trị mặc định thì để trống được, CSDL tự điền.
- Cột cho phép NULL, để trống thì gửi `null`. Riêng ô chọn để trống thì không gửi, nên lúc sửa không xóa về trống
  được.
- `CHECK` không hiện thành ô chọn, vì PostgREST không mô tả nó. Muốn có danh sách chọn thì dùng kiểu enum.
- Studio đặt sẵn kiểu `text` cho mọi cột chữ, nên cột chữ là ô nhiều dòng. Muốn ô một dòng thì đặt `varchar(n)`.
- Mảng enum: PostgREST không ghi giá trị enum cho cột mảng, nên trang lấy giá trị từ một cột thường cùng kiểu enum ở
  bảng bất kỳ của schema `sinh`. Không có cột nào như vậy thì cột mảng là ô chỉ đọc.
- Ô chỉ đọc không gửi gì: cột mảng `NOT NULL` cần giá trị mặc định, không thì thêm dòng bị CSDL từ chối.

## Nhãn hai thứ tiếng

Chú thích của bảng (`COMMENT ON TABLE`) và của cột (`COMMENT ON COLUMN`) viết theo dòng:

- dòng đầu: nhãn tiếng Việt;
- một dòng bắt đầu bằng `en:`: nhãn tiếng Anh, hiện khi trang ở tiếng Anh. Không có thì dùng nhãn tiếng Việt;
- các dòng còn lại: gợi ý dưới ô (bảng: lời giới thiệu), một thứ tiếng.

```sql
comment on table sinh.yeu_cau is 'Quản lý yêu cầu
en: Requests
Gửi yêu cầu tới phòng phụ trách và theo dõi tới khi xong.';
comment on column sinh.yeu_cau.tieu_de is 'Tiêu đề
en: Title';
```

## Tệp

| Tệp | Nội dung |
|---|---|
| `app.yaml` | Manifest: đường `/sinh`, image dựng từ thư mục này, 64 MiB. `database` chỉ vì manifest bắt buộc: schema trống `trang_sinh`, không migration. Bảng của các ứng dụng sinh ở schema `sinh`, do khung CSDL của lõi làm chủ |
| `public/openapi.js` | Mô tả API → menu, JSON Schema cho `schema-form.js`. Hàm thuần |
| `public/bao-cao.js` | Khai báo báo cáo → kiểm theo mô tả API, đường truy vấn hàm gộp, số liệu cho bảng và biểu đồ (cộng theo tháng, màu biểu đồ tròn). Hàm thuần |
| `public/rest.js` | Đường `/rest/v1`, đường in của svc-files (`duongIn`), tham số fetch (`Prefer: return=representation`, `count=exact` cho danh sách), đọc trả lời theo mã HTTP. 403 không kèm JSON là WAF ở cổng chặn, không phải thiếu quyền |
| `public/app.js` | Vẽ menu, biểu mẫu, danh sách; nạp lại mô tả khi quay lại tab (`visibilitychange`) |
| `public/auth.js`, `server.py`, `Dockerfile`, `public/style.css` | Như `apps/nghi-phep`: trang tĩnh Python thư viện chuẩn, không root; đăng nhập PKCE bằng client `app-sinh` |
| `public/i18n.js` | Bảng dịch vi/en của trang. Tên bảng, nhãn ô lấy từ COMMENT trong CSDL (tiếng Anh ở dòng `en:`) |
| `tests/` | `node --test tests/*.test.js`: bộ đổi mô tả API (cả màn "thêm cột Mức ưu tiên"; ô theo kiểu cột, nhãn `en:`, ô JSON, ô ngày giờ), cách gọi `/rest/v1`, bảng dịch, báo cáo (`bao-cao.test.js`: khai báo, truy vấn, cộng theo tháng; giá trị enum khớp migration), đường in và khi nào có nút In (`in.test.js`). `python3 -m unittest discover -s tests`: máy chủ trang thật trên cổng ngẫu nhiên |

`tests/postgrest-v14-openapi.json` là mô tả thật của PostgREST v14.18 lấy từ bộ thử trên CI (bảng mẫu `sinh.yeu_cau`).
`tests/postgrest-openapi.json` viết tay theo đúng dạng đó cho các ca bản thật chưa có: khóa ngoại, json, mảng, bảng
không chú thích, chú thích nhiều dòng.

## Chưa làm

- Xóa dòng, phân trang (chỉ 50 dòng mới nhất), lọc, tìm.
- Sửa giá trị cột mảng không phải enum; gợi ý dưới ô hai thứ tiếng.
- Báo cáo: lọc theo khoảng ngày hay giá trị, điền tháng trống, xuất tệp; nhiều cột nhóm.
- In: mở PDF ở tab mới (trình chặn cửa sổ bật lên chặn sau `await`), xem trước mẫu trên trang.

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

"""Ghi chú phát hành (scripts/release-notes.sh, dùng ở release.sh và .github/workflows/release.yml): lấy đúng mục
"## [X.Y.Z]" của CHANGELOG; khối mẫu trong chú thích HTML không tính; thiếu mục, hay mục chỉ có tiêu đề nhóm, thì
lỗi chứ không ra ghi chú rỗng. Không phát hành lại: release.sh dừng trước khi gắn khi thẻ đã có trên origin hay ở máy,
không hỏi được origin cũng dừng; máy không có sha256sum (macOS) thì dùng shasum -a 256, thiếu cả hai thì dừng trước khi
gắn thẻ (#57); có khóa ký (user.signingkey) thì thẻ ký và reconciler bật MOC_GITOPS_ALLOWED_SIGNERS nhận nó, ký
lỗi thì dừng khi chưa có thẻ, không có khóa thì báo rõ thẻ không ký (#492), ký bằng khóa GPG cũng báo vì reconciler
chỉ nhận chữ ký SSH (#514); release.yml dừng khi thẻ đã có Release,
kể cả nháp (chạy lệnh của bước với gh giả), và
báo lỗi khi action không tải lên đủ bốn tệp (gói, SBOM, hai .sha256). Trang Release (scripts/release_body.py): dòng chỉ
gói .tar.gz chính thức và SBOM, phần tóm tắt đầu mục, toàn bộ ghi chép gập trong <details>, dòng tiếp nối nối lại.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "release-notes.sh"
RELEASE = SCRIPT.parent / "release.sh"
BODY = SCRIPT.parent / "release_body.py"
spec = importlib.util.spec_from_file_location("release_body", BODY)
release_body = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_body)
spec = importlib.util.spec_from_file_location("reconcile_phat_hanh", SCRIPT.parent / "reconcile.py")
reconcile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)
WORKFLOW = SCRIPT.parent.parent / ".github" / "workflows" / "release.yml"
PACKAGE_FILES = ["scripts/kiem_goi.py", "scripts/license-header.sh", "VERSION", ".gitattributes", "LICENSE", "NOTICE",
                 "LICENSES/Apache-2.0.txt", "LICENSES/CC-BY-4.0.txt", "LICENSES/LicenseRef-Logos.txt",
                 "LICENSES/LicenseRef-VN-SHTT-Dieu-15.txt", "REUSE.toml"]
# repo thử không đọc cấu hình git của máy (khóa ký thẻ, hook…), tên người gắn thẻ cố định; bỏ mọi GIT_* thừa hưởng —
# chạy từ hook git thì GIT_DIR, GIT_INDEX_FILE trỏ về repo thật và lệnh git của test sẽ ghi vào đó
GIT_ENV = {
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    # không chạy bảo trì tự động sau commit/push: nó có thể tách nền và còn ghi vào objects/ lúc test xóa kho tạm
    # (CI git 2.55: "Directory not empty: 'objects'", xem test_moc_neo.GIT_ENV)
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "maintenance.auto",
    "GIT_CONFIG_VALUE_0": "false",
    "GIT_AUTHOR_NAME": "thu",
    "GIT_AUTHOR_EMAIL": "thu@example.invalid",
    "GIT_COMMITTER_NAME": "thu",
    "GIT_COMMITTER_EMAIL": "thu@example.invalid",
}

CHANGELOG = """# Nhật ký thay đổi

## [Chưa phát hành]

### Đã thêm
- Việc chưa phát hành.

## [0.2.0] - 2026-10-30

### Đã thêm
- Tính năng của 0.2.0.

### Đã sửa lỗi
- Lỗi của 0.2.0.

## [0.1.0] - 2026-10-18

### Đã thêm
- Khung dự án.

<!-- Mẫu cho bản phát hành kế tiếp:
## [0.3.0] - YYYY-MM-DD
### Đã thêm
### Đã sửa lỗi
-->
"""


class ReleaseNotesTest(unittest.TestCase):
    def notes(self, version: str, text: str = CHANGELOG) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "CHANGELOG.md"
            path.write_text(text, encoding="utf-8")
            return subprocess.run(["bash", str(SCRIPT), version, str(path)], capture_output=True, text=True)

    def test_takes_exactly_one_section(self) -> None:
        proc = self.notes("0.2.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "### Đã thêm\n- Tính năng của 0.2.0.\n\n### Đã sửa lỗi\n- Lỗi của 0.2.0.\n")

    def test_last_section_stops_before_template_comment(self) -> None:
        proc = self.notes("0.1.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "### Đã thêm\n- Khung dự án.\n")

    def test_template_heading_in_comment_is_not_a_release(self) -> None:
        proc = self.notes("0.3.0")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("chưa có mục '## [0.3.0]'", proc.stderr)

    def test_missing_or_heading_only_section_fails(self) -> None:
        self.assertEqual(self.notes("0.9.0").returncode, 1)
        empty = CHANGELOG.replace("- Tính năng của 0.2.0.\n", "").replace("- Lỗi của 0.2.0.\n", "")
        self.assertEqual(self.notes("0.2.0", empty).returncode, 1)

    def test_version_dots_are_literal(self) -> None:
        # "0.2.0" không được khớp "0a2b0"; "0.1.1" không được khớp mục "0.1.10"
        odd = CHANGELOG.replace("## [0.2.0]", "## [0a2b0]").replace("## [0.1.0]", "## [0.1.10]")
        self.assertEqual(self.notes("0.2.0", odd).returncode, 1)
        self.assertEqual(self.notes("0.1.1", odd).returncode, 1)


class NoReReleaseTest(unittest.TestCase):
    """release.sh trên một repo tạm có origin là repo bare cục bộ."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.repo = root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(RELEASE, self.repo / "scripts" / "release.sh")
        shutil.copy(SCRIPT, self.repo / "scripts" / "release-notes.sh")
        # release.sh kiểm gói vừa đóng (scripts/kiem_goi.py, test_kiem_goi.py): gói cần đủ tệp giấy phép và VERSION
        for rel in PACKAGE_FILES:
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(SCRIPT.parent.parent / rel, self.repo / rel)
        (self.repo / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
        (self.repo / ".gitignore").write_text("dist/\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-qm", "khởi tạo")
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], env=GIT_ENV, check=True)
        # receive-pack của kho trần không nhận biến GIT_CONFIG_* (git bỏ chúng khi đẩy qua đường dẫn cục bộ)
        subprocess.run(["git", "-C", str(self.origin), "config", "maintenance.auto", "false"], env=GIT_ENV, check=True)
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "origin", "main")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, env=GIT_ENV, capture_output=True, text=True,
                              check=True).stdout

    def release(self, version: str = "0.2.0", path: str | None = None) -> subprocess.CompletedProcess[str]:
        env = GIT_ENV if path is None else {**GIT_ENV, "PATH": path}
        return subprocess.run(["bash", "scripts/release.sh", version], cwd=self.repo, env=env, capture_output=True,
                              text=True)

    def path_without(self, *tools: str) -> str:
        """PATH chỉ có lối tắt tới các lệnh của PATH thật trừ tools: như máy không cài chúng (macOS thiếu sha256sum)."""
        bin_dir = self.repo.parent / "bin"
        bin_dir.mkdir()
        seen = set(tools)
        for folder in os.environ["PATH"].split(os.pathsep):
            if not os.path.isdir(folder):
                continue
            for entry in os.scandir(folder):
                if entry.name not in seen and entry.is_file() and os.access(entry.path, os.X_OK):
                    seen.add(entry.name)
                    (bin_dir / entry.name).symlink_to(entry.path)
        return str(bin_dir)

    def assert_nothing_made(self, proc: subprocess.CompletedProcess[str], message: str) -> None:
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(message, proc.stderr)
        self.assertFalse((self.repo / "dist").exists())

    def test_new_version_is_tagged_and_packed(self) -> None:
        proc = self.release()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.git("tag", "-l").split(), ["v0.2.0"])
        self.assertTrue((self.repo / "dist" / "signet-0.2.0.tar.gz").is_file())
        self.assertTrue((self.repo / "dist" / "signet-0.2.0.tar.gz.sha256").is_file())

    def test_tag_already_on_origin_stops_before_tagging(self) -> None:
        # thẻ đã đẩy từ máy khác: máy này chưa có, gắn được thẻ cục bộ nhưng đẩy lên sẽ là phát hành lại
        self.git("tag", "-a", "v0.2.0", "-m", "đã phát hành")
        self.git("push", "-q", "origin", "v0.2.0")
        self.git("tag", "-d", "v0.2.0")
        self.assert_nothing_made(self.release(), "đã có trên origin")
        self.assertEqual(self.git("tag", "-l"), "")

    def test_local_tag_stops(self) -> None:
        # lần trước gắn thẻ rồi dừng giữa chừng: chưa đẩy, gợi ý gỡ thẻ chứ không bảo lên phiên bản
        self.git("tag", "-a", "v0.2.0", "-m", "gắn dở")
        proc = self.release()
        self.assert_nothing_made(proc, "đã có ở máy này nhưng chưa đẩy lên origin")
        self.assertIn("git tag -d v0.2.0", proc.stderr)

    def test_tag_on_both_sides_is_released(self) -> None:
        self.git("tag", "-a", "v0.2.0", "-m", "đã phát hành")
        self.git("push", "-q", "origin", "v0.2.0")
        self.assert_nothing_made(self.release(), "đã có trên origin")

    def test_unreachable_origin_stops(self) -> None:
        self.git("remote", "set-url", "origin", str(self.origin.parent / "khong-co.git"))
        self.assert_nothing_made(self.release(), "không hỏi được origin")
        self.assertEqual(self.git("tag", "-l"), "")

    def test_without_origin_still_releases(self) -> None:
        # gói nguồn giải nén rồi git init (không có remote): không có gì để kiểm, vẫn phát hành được
        self.git("remote", "remove", "origin")
        self.assertEqual(self.release().returncode, 0)

    def test_other_version_is_not_blocked(self) -> None:
        self.git("tag", "-a", "v0.1.0", "-m", "bản cũ")
        self.git("push", "-q", "origin", "v0.1.0")
        # bản mới ở commit sau thẻ cũ: hai thẻ gắn cùng giây trên một commit thì VERSION của gói lấy nhầm thẻ cũ
        (self.repo / "MOI.md").write_text("Thay đổi của 0.2.0\n", encoding="utf-8")
        self.git("add", "MOI.md")
        self.git("commit", "-qm", "thay đổi")
        self.assertEqual(self.release("0.2.0").returncode, 0)

    def test_shasum_when_sha256sum_is_missing(self) -> None:
        # macOS (#57): có shasum, không có sha256sum — .sha256 vẫn đúng dòng "<băm>  <tên gói>" mà sha256sum -c đọc
        if shutil.which("shasum") is None:
            self.skipTest("máy này không có shasum")
        proc = self.release(path=self.path_without("sha256sum"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        package = self.repo / "dist" / "signet-0.2.0.tar.gz"
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        self.assertEqual((self.repo / "dist" / "signet-0.2.0.tar.gz.sha256").read_text(), f"{digest}  {package.name}\n")

    def test_unsigned_tag_is_reported(self) -> None:
        # người phát hành chưa có khóa ký: vẫn phát hành, nhưng báo rõ máy chủ kiểm chữ ký sẽ không tự nâng (#492)
        proc = self.release()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("thẻ v0.2.0 KHÔNG KÝ", proc.stderr)
        self.assertNotIn("SIGNATURE", self.git("cat-file", "tag", "v0.2.0"))

    @unittest.skipUnless(shutil.which("ssh-keygen"), "cần ssh-keygen")
    def test_ssh_key_signs_the_tag_and_gitops_accepts_it(self) -> None:
        keys = {}
        for name in ("phat-hanh", "la"):
            keys[name] = self.repo.parent / name
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(keys[name])],
                           check=True)
        self.git("config", "gpg.format", "ssh")
        self.git("config", "user.signingkey", f"{keys['phat-hanh']}.pub")
        proc = self.release()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("KHÔNG KÝ", proc.stderr)
        self.assertIn("-----BEGIN SSH SIGNATURE-----", self.git("cat-file", "tag", "v0.2.0"))
        # đúng phép kiểm của reconciler khi MOC_GITOPS_FOLLOW=release và đặt MOC_GITOPS_ALLOWED_SIGNERS: nhận thẻ ký
        # bằng khóa trong danh sách, từ chối khi danh sách chỉ có khóa khác
        git = ["git", "-C", str(self.repo)]
        signers = self.repo.parent / "allowed_signers"
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}):
            for name, accepted in (("phat-hanh", True), ("la", False)):
                with self.subTest(signer=name):
                    kind, key = (keys[name].parent / f"{name}.pub").read_text().split()[:2]
                    signers.write_text(f'{name} namespaces="git" {kind} {key}\n', encoding="utf-8")
                    if accepted:
                        reconcile.verify_signature(git, "v0.2.0", str(signers), tag=True)
                    else:
                        with self.assertRaises(reconcile.ReconcileError):
                            reconcile.verify_signature(git, "v0.2.0", str(signers), tag=True)

    @unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgconf"), "cần gpg")
    def test_gpg_signed_tag_is_reported(self) -> None:
        # khóa ký là khóa GPG (thường dùng ký commit trên GitHub): thẻ có chữ ký PGP mà reconciler chỉ nhận SSH, nên
        # phải báo như thẻ không ký (#514)
        home = self.repo.parent / "gnupg"
        home.mkdir(mode=0o700)
        self.addCleanup(subprocess.run, ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"], check=False)
        env = {**GIT_ENV, "GNUPGHOME": str(home)}
        subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", "Phat hanh <ph@example.org>",
                        "ed25519", "sign", "never"], env=env, check=True, capture_output=True)
        self.git("config", "user.signingkey", "ph@example.org")
        with mock.patch.dict(GIT_ENV, {"GNUPGHOME": str(home)}):
            proc = self.release()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-----BEGIN PGP SIGNATURE-----", self.git("cat-file", "tag", "v0.2.0"))
        self.assertIn("thẻ v0.2.0 KHÔNG KÝ bằng khóa SSH", proc.stderr)

    def test_signing_error_stops_before_tagging(self) -> None:
        # chương trình ký lỗi (khóa hỏng, ssh-agent không có khóa…): không để lại thẻ không ký thay cho thẻ ký
        self.git("config", "gpg.format", "ssh")
        self.git("config", "gpg.ssh.program", "false")
        self.git("config", "user.signingkey", str(self.repo.parent / "khoa.pub"))
        self.assert_nothing_made(self.release(), "không ký được thẻ v0.2.0")
        self.assertEqual(self.git("tag", "-l"), "")

    def test_no_hashing_tool_stops_before_tagging(self) -> None:
        proc = self.release(path=self.path_without("sha256sum", "shasum"))
        self.assert_nothing_made(proc, "không có sha256sum hay shasum")
        self.assertEqual(self.git("tag", "-l"), "")


def step_script(name: str) -> str:
    """Khối `run: |` của bước `name` trong release.yml, bỏ thụt lề (không có PyYAML)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    i = lines.index(f"      - name: {name}")
    while lines[i].strip() != "run: |":
        i += 1
    indent = len(lines[i]) - len(lines[i].lstrip()) + 2
    body = []
    for line in lines[i + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body).strip() + "\n"


# gh giả: chỉ hiểu `gh api … --jq <bộ lọc>`, áp bộ lọc lên danh sách Release trong $FAKE_RELEASES như gh --jq
FAKE_GH = """#!/usr/bin/env bash
[ -z "${FAKE_GH_FAIL:-}" ] || { echo "gh: $FAKE_GH_FAIL" >&2; exit 1; }
echo "$*" >> "$FAKE_GH_CALLS"
while [ $# -gt 0 ]; do [ "$1" = --jq ] && filter="$2"; shift; done
jq -r "$filter" "$FAKE_RELEASES"
"""


@unittest.skipUnless(shutil.which("jq"), "cần jq (runner ubuntu của GitHub có sẵn)")
class WorkflowNoReReleaseTest(unittest.TestCase):
    """release.yml: chạy thật lệnh của bước "Chặn phát hành lại" (bash -e như runner) với gh giả, và bước kiểm gói."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / "gh").write_text(FAKE_GH, encoding="utf-8")
        (self.dir / "gh").chmod(0o755)

    def guard(self, releases: list[dict], fail: str = "") -> subprocess.CompletedProcess[str]:
        (self.dir / "releases.json").write_text(json.dumps(releases), encoding="utf-8")
        env = {**os.environ, "PATH": f"{self.dir}:{os.environ['PATH']}", "GITHUB_REPOSITORY": "HIT-Champion/Signet",
               "GITHUB_REF_NAME": "v0.2.0", "FAKE_RELEASES": str(self.dir / "releases.json"),
               "FAKE_GH_CALLS": str(self.dir / "calls"), "FAKE_GH_FAIL": fail}
        return subprocess.run(["bash", "-e", "-c", step_script("Chặn phát hành lại")], env=env, capture_output=True,
                              text=True)

    @staticmethod
    def release(tag: str, draft: bool = False) -> dict:
        return {"tag_name": tag, "draft": draft, "html_url": f"https://github.com/HIT-Champion/Signet/releases/{tag}"}

    def test_new_tag_passes_and_lists_every_page(self) -> None:
        proc = self.guard([self.release("v0.1.0"), self.release("v0.2.0-rc.1", draft=True), self.release("v0.2.00")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        calls = (self.dir / "calls").read_text(encoding="utf-8")
        self.assertIn("--paginate", calls)
        self.assertIn("repos/HIT-Champion/Signet/releases?per_page=100", calls)

    def test_published_release_stops(self) -> None:
        proc = self.guard([self.release("v0.1.0"), self.release("v0.2.0")])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::v0.2.0 đã có Release (đã đăng https://github.com/HIT-Champion/Signet/releases/v0.2.0)",
                      proc.stdout)

    def test_draft_left_by_deleted_tag_stops(self) -> None:
        # xóa thẻ của Release đã đăng → GitHub chuyển Release thành nháp; releases/tags/<thẻ> không thấy nháp
        proc = self.guard([self.release("v0.2.0", draft=True)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("(nháp https://", proc.stdout)

    def test_gh_error_stops(self) -> None:
        proc = self.guard([], fail="HTTP 502")
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.dir / "calls").exists())

    def test_guard_runs_before_release_action(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        guard = text.index("name: Chặn phát hành lại")
        self.assertLess(guard, text.index("name: Sinh gói nguồn .tar.gz"))
        self.assertLess(guard, text.index("softprops/action-gh-release@"))

    def assets(self, value: str | None) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k != "ASSETS"} | ({} if value is None else {"ASSETS": value})
        return subprocess.run(["bash", "-e", "-c", step_script("Kiểm gói đã tải lên")], env=env, capture_output=True,
                              text=True)

    def test_upload_check_needs_all_four_files(self) -> None:
        names = ["signet-0.2.0.tar.gz", "signet-0.2.0.tar.gz.sha256", "signet-0.2.0.cdx.json",
                 "signet-0.2.0.cdx.json.sha256"]
        self.assertEqual(self.assets(json.dumps([{"name": n} for n in names])).returncode, 0)
        skipped = self.assets(json.dumps([{"name": n} for n in names[1:]]))
        self.assertEqual(skipped.returncode, 1)
        self.assertIn("Chỉ tải lên 3/4 tệp", skipped.stdout)
        self.assertEqual(self.assets(None).returncode, 1)

    def test_action_does_not_overwrite_assets(self) -> None:
        action = WORKFLOW.read_text(encoding="utf-8").split("softprops/action-gh-release@", 1)[1]
        self.assertIn("overwrite_files: false", action)
        self.assertIn("fail_on_unmatched_files: true", action)
        self.assertIn("ASSETS: ${{ steps.gh_release.outputs.assets }}", action)

    def test_sbom_is_made_from_the_tag_and_attached(self) -> None:
        # make sbom sinh dist/signet-$V.cdx.json (+ .sha256) trước khi tạo Release; action tải cả hai lên
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertLess(text.index("name: Sinh SBOM CycloneDX (make sbom)"), text.index("softprops/action-gh-release@"))
        self.assertIn('run: make sbom VERSION="$V"', text)
        files = text.split("files: |", 1)[1]
        self.assertIn("dist/*.cdx.json\n", files)
        self.assertIn("dist/*.cdx.json.sha256\n", files)


class ReleaseBodyTest(unittest.TestCase):
    """scripts/release_body.py: trang Release ngắn — tóm tắt hiện ra, ghi chép đầy đủ gập lại, không gãy dòng."""

    URL = "https://github.com/HIT-Champion/Signet"
    NOTES = ("Bản cho vòng trường: văn bản đến và văn bản đi chạy đủ luồng,\n"
             "dựng từ mã nguồn bằng make.\n"
             "\n"
             "- Văn bản đi: soạn, duyệt, ký,\n"
             "  cấp số, phát hành PDF có mã QR.\n"
             "\n"
             "### Đã thêm\n"
             "- Cổng xác thực, xem [docs/api/](docs/api/README.md) và\n"
             "  [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/).\n"
             "- Sổ đăng ký.\n"
             "\n"
             "### Đã sửa lỗi\n"
             "- Lỗi gấp.\n")

    def test_summary_shows_and_changes_fold(self) -> None:
        out = release_body.body("1.1.0", self.NOTES, self.URL)
        head, rest = out.split("<details>", 1)
        self.assertTrue(head.startswith("**Gói phát hành chính thức: `signet-1.1.0.tar.gz`**"))
        self.assertIn("`sha256sum -c signet-1.1.0.tar.gz.sha256`", head)
        self.assertIn("(SBOM CycloneDX): `signet-1.1.0.cdx.json`", head)
        self.assertIn('"Source code (zip)"', head)
        self.assertIn("\n\nBản cho vòng trường: văn bản đến và văn bản đi chạy đủ luồng, dựng từ mã nguồn bằng "
                      "make.\n\n- Văn bản đi: soạn, duyệt, ký, cấp số, phát hành PDF có mã QR.\n\n", head)
        self.assertNotIn("### Đã thêm", head)
        self.assertIn("<summary>Toàn bộ ghi chép thay đổi của 1.1.0 (3 mục)</summary>\n\n### Đã thêm\n", rest)
        self.assertTrue(rest.endswith("- Lỗi gấp.\n\n</details>\n"))

    def test_continuation_lines_join_and_relative_links_point_at_the_tag(self) -> None:
        out = release_body.body("1.1.0", self.NOTES, self.URL)
        self.assertIn("- Cổng xác thực, xem [docs/api/](https://github.com/HIT-Champion/Signet/blob/v1.1.0/docs/api/"
                      "README.md) và [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/).\n- Sổ đăng ký.\n\n"
                      "### Đã sửa lỗi\n", out)

    def test_without_summary_only_the_folded_changes(self) -> None:
        out = release_body.body("1.1.1", "### Đã sửa lỗi\n- Lỗi gấp.\n", self.URL)
        first, second = out.split("\n\n", 1)
        self.assertIn("`signet-1.1.1.tar.gz`", first)
        self.assertTrue(second.startswith("<details>\n<summary>Toàn bộ ghi chép thay đổi của 1.1.1 (1 mục)</summary>"))

    def test_entry_reads_the_section_and_fails_without_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "CHANGELOG.md"
            path.write_text(CHANGELOG, encoding="utf-8")
            ok = subprocess.run([sys.executable, str(BODY), "0.2.0", str(path)], capture_output=True, text=True)
            missing = subprocess.run([sys.executable, str(BODY), "0.3.0", str(path)], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("(2 mục)</summary>\n\n### Đã thêm\n- Tính năng của 0.2.0.\n\n### Đã sửa lỗi\n", ok.stdout)
        self.assertNotIn("Khung dự án", ok.stdout)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("chưa có mục '## [0.3.0]'", missing.stderr)
        self.assertEqual(missing.stdout, "")


class WorkflowNotesTest(unittest.TestCase):
    """release.yml, bước "Trích ghi chú phát hành từ CHANGELOG": chạy thật lệnh của bước — trang Release dựng bằng
    release_body.py; thiếu mục thì dừng."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / "scripts").mkdir()
        shutil.copy(SCRIPT, self.dir / "scripts" / "release-notes.sh")
        shutil.copy(BODY, self.dir / "scripts" / "release_body.py")
        (self.dir / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
        (self.dir / "dist").mkdir()

    def step(self, version: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "-e", "-c", step_script("Trích ghi chú phát hành từ CHANGELOG")], cwd=self.dir,
                              env={**os.environ, "V": version}, capture_output=True, text=True)

    def test_page_starts_with_the_official_package(self) -> None:
        proc = self.step("0.2.0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        page = (self.dir / "dist" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        self.assertTrue(page.startswith("**Gói phát hành chính thức: `signet-0.2.0.tar.gz`**"))
        self.assertIn("- Tính năng của 0.2.0.\n", page)

    def test_missing_section_stops(self) -> None:
        proc = self.step("0.3.0")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::CHANGELOG.md chưa có mục [0.3.0]", proc.stdout)


class ImageJobTest(unittest.TestCase):
    """release.yml, job image (#344): mỗi image compose dựng là một dòng ma trận cùng thư mục, cùng build context phụ;
    chỉ job này ghi GHCR; PR chỉ dựng, thẻ mới đẩy; không thêm action, không phụ thuộc job gói nguồn."""

    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.job = self.text[self.text.index("\n  image:\n"):]

    def test_matrix_covers_every_image_compose_builds(self) -> None:
        compose = (WORKFLOW.parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
        built = set()
        pairs = re.findall(r"\n    build: (.+)\n    image: moc/([a-z0-9-]+):\$\{MOC_VERSION:-dev\}\n", compose)
        for build, name in pairs:
            if build.startswith("{"):
                context = re.search(r"context: \./([^,}]+)", build).group(1)
                extra = re.findall(r"(\w+): \./([^,}]+)", build.partition("additional_contexts:")[2])
                built.add((name, context, ",".join(f"{k}={v}" for k, v in extra)))
            else:
                built.add((name, build.removeprefix("./"), ""))
        self.assertEqual(len(built), compose.count("\n    build: "))
        rows = {(n, c, e) for n, c, e in re.findall(
            r"- \{name: ([a-z0-9-]+), context: ([^,}]+)(?:, extra: ([^}]+))?\}", self.job)}
        self.assertEqual(rows, built)

    def test_only_tags_push_and_only_this_job_writes_packages(self) -> None:
        self.assertIn("\npermissions: {}\n", self.text)
        self.assertEqual(self.text.count("packages: write"), 1)
        self.assertIn("packages: write", self.job)
        release = self.text[self.text.index("\n  release:\n"):self.text.index("\n  image:\n")]
        self.assertIn("    if: github.event_name == 'push'\n", release)       # PR không đăng Release
        self.assertIn('if [ "$GITHUB_EVENT_NAME" = push ]; then args+=(--push)\n', self.job)
        self.assertIn('else args+=(--output "type=oci,dest=$RUNNER_TEMP/image.tar"); fi\n', self.job)
        self.assertIn("--sbom=true --provenance=mode=max", self.job)
        self.assertNotIn("\n  workflow_dispatch", self.text)
        self.assertEqual(re.findall(r"uses: ([^@\s]+)@", self.job), ["actions/checkout"])
        self.assertIn("persist-credentials: false", self.job)
        self.assertNotIn("needs:", self.job)

    def version(self, event: str, tag: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.NamedTemporaryFile("r", encoding="utf-8") as out:
            env = {**GIT_ENV, "GITHUB_EVENT_NAME": event, "GITHUB_REF_NAME": tag, "GITHUB_REF": f"refs/tags/{tag}",
                   "GITHUB_OUTPUT": out.name}
            proc = subprocess.run(["bash", "-e", "-c", step_script("Phiên bản của image")], env=env,
                                  capture_output=True, text=True)
            return proc, out.read()

    def test_pull_request_builds_under_a_placeholder_tag(self) -> None:
        proc, out = self.version("pull_request", "613/merge")
        self.assertEqual((proc.returncode, out), (0, "version=pr\n"), proc.stderr)

    def attested(self, predicates: list[str]) -> subprocess.CompletedProcess[str]:
        """Chạy bước "Kiểm SBOM và provenance trong image" trên tệp OCI dựng tay như buildx xuất: index.json → chỉ mục
        của image → manifest image và manifest attestation có các lớp mang predicate-type."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        blobs: dict[str, bytes] = {}

        def put(doc: dict) -> str:
            raw = json.dumps(doc).encode()
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            blobs[digest] = raw
            return digest
        layers = [{"digest": "sha256:" + "0" * 64, "annotations": {"in-toto.io/predicate-type": p}} for p in predicates]
        image = put({"layers": [{"digest": "sha256:" + "1" * 64}]})
        attestation = put({"layers": layers})
        inner = put({"manifests": [{"digest": image}, {"digest": attestation, "annotations": {
            "vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": image}}]})
        with tarfile.open(pathlib.Path(tmp.name, "image.tar"), "w") as tar:
            for name, raw in [("index.json", json.dumps({"manifests": [{"digest": inner}]}).encode()),
                              *((f"blobs/{d.replace(':', '/')}", raw) for d, raw in blobs.items())]:
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))
        return subprocess.run(["bash", "-e", "-c", step_script("Kiểm SBOM và provenance trong image")],
                              env={**os.environ, "RUNNER_TEMP": tmp.name}, capture_output=True, text=True)

    def test_pull_request_image_carries_sbom_and_provenance(self) -> None:
        proc = self.attested(["https://spdx.dev/Document", "https://slsa.dev/provenance/v0.2"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Attestation: https://slsa.dev/provenance/v0.2, https://spdx.dev/Document", proc.stdout)

    def test_image_without_provenance_or_sbom_fails(self) -> None:
        for predicates in (["https://spdx.dev/Document"], ["https://slsa.dev/provenance/v1"], []):
            proc = self.attested(predicates)
            self.assertEqual(proc.returncode, 1, predicates)
            self.assertIn("::error::Image thiếu SBOM hoặc provenance", proc.stdout)

    def test_tag_with_shell_characters_stops(self) -> None:
        proc, out = self.version("push", "v1.0.0$(id)")
        self.assertEqual((proc.returncode, out), (1, ""))
        self.assertIn("::error::Thẻ 'v1.0.0$(id)' không đúng dạng", proc.stdout)

if __name__ == "__main__":
    unittest.main()

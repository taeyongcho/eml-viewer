"""
IMAP 메일 받아오기 + EML 파일로 저장
"""
import imaplib, email, email.policy, os, re, threading
from pathlib import Path


def sanitize_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s)[:80]


def fetch_imap(account: dict, save_dir: str,
               on_progress=None, on_done=None, on_error=None,
               folder="INBOX", limit=200):
    """
    IMAP 서버에서 메일 받아 save_dir 에 .eml 로 저장.
    on_progress(done, total) 콜백으로 진행 상황 전달.
    """
    def worker():
        try:
            if account["imap_ssl"]:
                conn = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
            else:
                conn = imaplib.IMAP4(account["imap_host"], account["imap_port"])

            conn.login(account["username"], account["password"])
            conn.select(folder, readonly=True)

            # 전체 메일 ID 목록 (최신 limit개)
            _, data = conn.search(None, "ALL")
            all_ids = data[0].split()
            ids = all_ids[-limit:]  # 최신 N개
            total = len(ids)
            saved = 0
            skipped = 0

            Path(save_dir).mkdir(parents=True, exist_ok=True)

            for i, uid in enumerate(reversed(ids)):  # 최신부터
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]

                # 파일명: 날짜_제목.eml
                msg = email.message_from_bytes(raw, policy=email.policy.compat32)
                date_str = msg.get("Date", "")
                subj = msg.get("Subject", "")
                # 날짜 간단 파싱
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(date_str)
                    prefix = dt.strftime("%Y%m%d_%H%M%S")
                except Exception:
                    prefix = f"{i:05d}"

                subj_decoded = ""
                try:
                    import email.header
                    parts = email.header.decode_header(subj)
                    for part, charset in parts:
                        if isinstance(part, bytes):
                            subj_decoded += part.decode(charset or "utf-8", errors="replace")
                        else:
                            subj_decoded += str(part)
                except Exception:
                    subj_decoded = subj or "no_subject"

                fname = f"{prefix}_{sanitize_filename(subj_decoded)}.eml"
                fpath = os.path.join(save_dir, fname)

                if os.path.exists(fpath):
                    skipped += 1
                else:
                    with open(fpath, "wb") as f:
                        f.write(raw)
                    saved += 1

                if on_progress:
                    on_progress(i + 1, total, saved, skipped)

            conn.logout()
            if on_done:
                on_done(saved, skipped, save_dir)

        except Exception as ex:
            if on_error:
                on_error(str(ex))

    threading.Thread(target=worker, daemon=True).start()

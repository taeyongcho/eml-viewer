"""
메일 작성 / 보내기 창
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import smtplib, ssl, email.mime.text, email.mime.multipart, email.mime.base
import email.encoders, os
from pathlib import Path


class ComposeWindow(tk.Toplevel):
    def __init__(self, parent, account: dict, reply_to: dict = None):
        super().__init__(parent)
        self.title("메일 작성")
        self.geometry("720x580")
        self.minsize(600, 460)
        self._account = account
        self._attachments = []  # [(filename, filepath)]
        self._build(reply_to)

    def _build(self, reply_to):
        # 헤더 영역
        hf = tk.Frame(self, pady=6, padx=10)
        hf.pack(fill="x")

        fields = [("받는 이 (To)", "to"), ("참조 (Cc)", "cc"), ("제목", "subject")]
        self._vars = {}
        for i, (lbl, key) in enumerate(fields):
            tk.Label(hf, text=lbl+":", width=13, anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar()
            self._vars[key] = v
            tk.Entry(hf, textvariable=v, width=60).grid(row=i, column=1, sticky="ew", pady=2, padx=(4,0))
        hf.columnconfigure(1, weight=1)

        # 보내는 이 표시
        from_lbl = f"보내는 이: {self._account['name']} <{self._account['email']}>"
        tk.Label(self, text=from_lbl, fg="#666", font=("Malgun Gothic", 9),
                 anchor="w", padx=10).pack(fill="x")

        tk.Frame(self, height=1, bg="#ddd").pack(fill="x", padx=10, pady=4)

        # 본문
        body_f = tk.Frame(self)
        body_f.pack(fill="both", expand=True, padx=10)
        self._body = tk.Text(body_f, font=("Malgun Gothic", 10), wrap="word",
                              relief="flat", padx=6, pady=6)
        vsb = ttk.Scrollbar(body_f, command=self._body.yview)
        self._body.configure(yscrollcommand=vsb.set)
        self._body.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 첨부파일 영역
        self._att_frame = tk.Frame(self, padx=10, pady=4)
        self._att_frame.pack(fill="x")

        # 버튼
        btn_f = tk.Frame(self, padx=10, pady=8)
        btn_f.pack(fill="x")
        tk.Button(btn_f, text="📎 첨부파일 추가", relief="groove", padx=8,
                  command=self._add_attach).pack(side="left")
        tk.Button(btn_f, text="✉ 보내기", relief="groove", padx=16,
                  command=self._send, font=("Malgun Gothic", 10, "bold")).pack(side="right")
        tk.Button(btn_f, text="취소", relief="groove", padx=10,
                  command=self.destroy).pack(side="right", padx=4)

        # 답장 자동 채우기
        if reply_to:
            self._vars["to"].set(reply_to.get("from_", ""))
            self._vars["subject"].set("Re: " + reply_to.get("subject", ""))
            orig = reply_to.get("body_text", "")
            if orig:
                sep = "\n\n--- 원본 메일 ---\n"
                self._body.insert("end", sep + orig)
                self._body.mark_set("insert", "1.0")

    def _add_attach(self):
        paths = filedialog.askopenfilenames(title="첨부파일 선택")
        for p in paths:
            fname = os.path.basename(p)
            self._attachments.append((fname, p))
            row = tk.Frame(self._att_frame)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"📎 {fname}", anchor="w",
                     font=("Malgun Gothic", 9)).pack(side="left")
            tk.Button(row, text="✕", relief="flat", fg="#e44", padx=4,
                      command=lambda r=row, item=(fname,p): self._remove_attach(r, item)
                      ).pack(side="right")

    def _remove_attach(self, row, item):
        if item in self._attachments:
            self._attachments.remove(item)
        row.destroy()

    def _send(self):
        to_str  = self._vars["to"].get().strip()
        cc_str  = self._vars["cc"].get().strip()
        subject = self._vars["subject"].get().strip()
        body    = self._body.get("1.0", "end").strip()

        if not to_str:
            messagebox.showwarning("입력 오류", "받는 이를 입력하세요.", parent=self)
            return

        a = self._account
        try:
            # 메시지 구성
            msg = email.mime.multipart.MIMEMultipart()
            msg["From"]    = f"{a['name']} <{a['email']}>"
            msg["To"]      = to_str
            if cc_str:
                msg["Cc"]  = cc_str
            msg["Subject"] = subject

            msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

            # 첨부파일
            for fname, fpath in self._attachments:
                with open(fpath, "rb") as f:
                    part = email.mime.base.MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                email.encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
                msg.attach(part)

            # SMTP 전송
            rcpts = [x.strip() for x in (to_str + ("," + cc_str if cc_str else "")).split(",") if x.strip()]
            ctx = ssl.create_default_context()

            if a["smtp_ssl"]:
                with smtplib.SMTP_SSL(a["smtp_host"], a["smtp_port"], context=ctx) as server:
                    server.login(a["username"], a["password"])
                    server.sendmail(a["email"], rcpts, msg.as_bytes())
            else:
                with smtplib.SMTP(a["smtp_host"], a["smtp_port"]) as server:
                    server.starttls(context=ctx)
                    server.login(a["username"], a["password"])
                    server.sendmail(a["email"], rcpts, msg.as_bytes())

            messagebox.showinfo("전송 완료", f"메일을 보냈습니다.\n받는 이: {to_str}", parent=self)
            self.destroy()

        except Exception as ex:
            messagebox.showerror("전송 실패", str(ex), parent=self)

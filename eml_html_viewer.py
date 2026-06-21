"""
HTML 뷰어 - 별도 프로세스로 pywebview 실행 (메인스레드 제한 우회)
"""
import subprocess, sys, os, tempfile

HAS_WEBVIEW = True


def _find_viewer():
    """html_viewer_proc 실행파일 또는 스크립트 경로 탐색"""
    base = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
    # .exe 빌드 환경
    exe = os.path.join(base, "html_viewer_proc.exe")
    if os.path.exists(exe):
        return [exe]
    # 스크립트 환경
    py = os.path.join(base, "html_viewer_proc.py")
    if os.path.exists(py):
        return [sys.executable, py]
    return None


class HtmlPanel:
    def __init__(self):
        self._proc = None
        self._tmp_path = None
        self._viewer_cmd = _find_viewer()

    def show(self, html_content: str, title: str = "HTML 미리보기"):
        # 임시 HTML 저장
        if self._tmp_path:
            try:
                os.unlink(self._tmp_path)
            except Exception:
                pass
        # UTF-8 charset 메타태그 보장
        content = html_content
        if content and "charset" not in content[:500].lower():
            if "<head>" in content[:200].lower():
                content = content.replace("<head>", '<head><meta charset="utf-8">', 1)
            elif "<html>" in content[:200].lower():
                content = content.replace("<html>", '<html><head><meta charset="utf-8"></head>', 1)
            else:
                content = '<meta charset="utf-8">' + content
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html",
                                          mode="w", encoding="utf-8")
        tmp.write(content)
        tmp.close()
        self._tmp_path = tmp.name

        # 이전 뷰어 프로세스가 살아있으면 재사용 (이미 열린 창에 새 URL 로드)
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

        if not self._viewer_cmd:
            return False  # 뷰어 없음 → 브라우저 폴백

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(
            self._viewer_cmd + [self._tmp_path, title],
            creationflags=flags
        )
        return True

    def close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

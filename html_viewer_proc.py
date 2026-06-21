"""
별도 프로세스로 실행되는 HTML 뷰어
pywebview는 메인 스레드 필요 → 이 파일 자체가 메인 스레드
"""
import sys

def main():
    if len(sys.argv) < 2:
        return
    html_path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else "HTML 미리보기"

    try:
        import webview
        w = webview.create_window(title, url=f"file:///{html_path}",
                                   width=960, height=700, resizable=True)
        webview.start()
    except Exception:
        # webview 실패 시 기본 브라우저로 폴백
        import webbrowser
        webbrowser.open(f"file:///{html_path}")

if __name__ == "__main__":
    main()

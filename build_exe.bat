@echo off
chcp 65001 >nul
echo ============================================
echo  Axiosoft EML ��� ���� ��ũ��Ʈ
echo ============================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [����] Python�� �����ϴ�. https://www.python.org ���� ��ġ �� ������ϼ���.
    pause
    exit /b 1
)
echo [1/4] ��Ű�� ��ġ ��...
pip install pyinstaller pillow pywebview -q
echo.
echo [2/4] HTML ��� �ܵ� exe ���� ��...
pyinstaller --onefile --windowed --name html_viewer_proc --hidden-import=webview --hidden-import=webview.platforms.winforms --collect-all webview html_viewer_proc.py
if errorlevel 1 (
    echo [���] HTML ��� ���� ���� - �⺻ �������� ��ü�˴ϴ�.
)
echo.
echo [3/4] ���� �� ���� �� (�ܵ� ���� exe)...
pyinstaller --onefile --windowed --name EML��� --icon icon.ico --hidden-import=email.mime.text --hidden-import=email.mime.multipart --hidden-import=email.mime.base --hidden-import=imaplib --hidden-import=smtplib --hidden-import=sqlite3 --hidden-import=eml_db --hidden-import=eml_account --hidden-import=eml_compose --hidden-import=eml_imap --hidden-import=eml_html_viewer --collect-submodules email eml_viewer.py
if errorlevel 1 (
    echo [����] ���� �� ���� ����.
    pause
    exit /b 1
)
echo.
echo [4/4] ����� ���� ��...
if not exist .\��� mkdir .\���
copy .\dist\EML���.exe .\���\EML���.exe >nul
if exist .\dist\html_viewer_proc.exe copy .\dist\html_viewer_proc.exe .\���\html_viewer_proc.exe >nul
echo.
echo ============================================
echo  �Ϸ�!
echo  EML_viewer.exe         <- ���� (�ܵ� ���� ����)
echo  html_viewer_proc.exe <- HTML ��� (���� ������ ������ �� �� HTML ���� ����)
echo                          ��� �⺻ �������� �ڵ� ��ü��
echo ============================================
echo.
pause

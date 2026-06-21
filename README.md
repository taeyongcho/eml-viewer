# 📧 EML 이메일 뷰어

## 기능
- .eml 파일 열기 (파일 선택 또는 폴더 전체 열기)
- 이메일 목록 정렬 (날짜 / 제목 / 보낸 이)
- 검색 및 필터 (제목 / 보낸 이 / 받는 이 / 본문)
- HTML 이메일 렌더링 (tkinterweb 설치 시) 또는 브라우저로 보기
- 첨부파일 저장
- 인쇄 (브라우저 인쇄 창 활용)
- 한글 인코딩 자동 처리 (UTF-8, EUC-KR, CP949)

---

## 설치 방법 (처음 한 번만)

### 필요한 것
- Windows 10/11
- Python 3.10 이상 (https://www.python.org)
  - 설치 시 **"Add Python to PATH"** 반드시 체크!

### 빌드 방법
1. 이 폴더 안에서 **`빌드하기.bat`** 를 더블클릭
2. 자동으로 패키지 설치 및 빌드 진행
3. 완료 후 **`출력\EML뷰어.exe`** 생성됨
4. 생성된 .exe 파일을 원하는 위치에 복사해서 사용

> 빌드 후에는 Python 없이도 .exe 단독 실행 가능

---

## 바로 실행 (빌드 없이 Python으로)

```
pip install tkinterweb
python eml_viewer.py
```

---

## HTML 이메일 렌더링

앱 내에서 HTML을 렌더링하려면 tkinterweb이 필요합니다:
```
pip install tkinterweb
```
설치하지 않아도 "브라우저로 HTML 보기" 버튼으로 기본 브라우저에서 볼 수 있습니다.

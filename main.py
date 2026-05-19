name: Auto Bus Data Fetcher (Every 15 min)

on:
  schedule:
    # 15分おきに実行
    # 混雑を避けるため、あえて「7分, 22分, 37分, 52分」という中途半端な時間に設定
    - cron: '7,22,37,52 * * * *'
  workflow_dispatch: # 手動実行ボタンを有効化

jobs:
  build:
    runs-on: ubuntu-latest
    # ログの時間を日本時間に合わせる
    env:
      TZ: 'Asia/Tokyo'

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          # rebaseを行うために履歴をすべて取得する設定
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests pandas

      - name: Run script
        run: |
          echo "Starting script at $(date)"
          python main.py

      - name: Commit and Push changes
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add .
          
          # [skip ci] を削除して、通常のコミットメッセージにする
          git commit -m "Update bus data: $(date +'%Y-%m-%d %H:%M:%S')" || exit 0
          
          git pull --rebase origin main
          git push origin main
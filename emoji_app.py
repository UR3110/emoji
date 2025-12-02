import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import time
import pandas as pd

# --- 設定項目 ---
# ローカルで動かす場合の鍵ファイル名
SERVICE_ACCOUNT_FILE = 'service_account.json'
# ★書き換えてください (スプレッドシートID)
SPREADSHEET_ID = 'ここにスプレッドシートIDを入力してください' 

# 分析対象のシート名（絵文字）リスト
SHEET_NAMES = [
    "😀", "😁", "😂", "😃", "😄", "😅", "😆", "😇", "😈", "😉",
    "😊", "😋", "😌", "😍", "😎", "😏", "😐", "😑", "😒", "😓",
    "😔", "😕", "😖", "😗", "😘", "😙", "😚", "😛", "😜", "😝",
    "😞", "😟", "😠", "😡", "😢", "😣", "😤", "😥", "😦", "😧",
    "😨", "😩", "😪", "😫", "😬", "😭", "😮", "😯", "😰", "😱",
    "😲", "😳", "😴", "😵", "😶", "😷", "😸", "😹", "😺", "😻",
    "😼", "😽", "😾", "😿", "🙀", "🙁", "🙂", "🙃", "🙄"
]

# --- 関数定義 ---

@st.cache_resource
def load_data():
    """スプレッドシートから学習データを読み込む (確率は無視して単語の存在のみチェック)"""
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 認証ロジック: Secrets (Cloud) か JSONファイル (Local) かを自動判定
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    else:
        try:
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scope)
        except FileNotFoundError:
            st.error("認証ファイルが見つかりません。")
            st.stop()

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    # {絵文字: {単語, 単語, ...}} の形式で保持（確率は不要なのでセットで管理）
    emoji_keywords = {}
    all_words = set()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_sheets = len(SHEET_NAMES)
    
    for i, sheet_name in enumerate(SHEET_NAMES):
        status_text.text(f"データを読み込み中... ({i+1}/{total_sheets}) {sheet_name}")
        
        # 429エラー対策のリトライ処理
        max_retries = 3
        for attempt in range(max_retries):
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                rows = worksheet.get_all_values()
                
                keywords = set()
                # ヘッダー判定（1行目の2列目に'%'が含まれていればヘッダーありとみなす）
                start_row = 1 if rows and len(rows) > 0 and len(rows[0]) > 1 and '%' in str(rows[0][1]) else 0

                for row in rows[start_row:]:
                    # 名詞(0), 動詞(2), 形容詞(4) の列にある単語を取得
                    for col_idx in [0, 2, 4]:
                        if len(row) > col_idx and row[col_idx]:
                            word = row[col_idx].strip()
                            if word:
                                keywords.add(word)
                                all_words.add(word)
                
                emoji_keywords[sheet_name] = keywords
                break # 成功したらループを抜ける
                
            except gspread.exceptions.WorksheetNotFound:
                break # シートがない場合はスキップ
            except gspread.exceptions.APIError as e:
                if "429" in str(e):
                    time.sleep((2 ** attempt) * 2)
                else:
                    break
            except Exception:
                break
        
        time.sleep(1.5) # API制限回避
        progress_bar.progress((i + 1) / total_sheets)

    status_text.empty()
    progress_bar.empty()
    
    return emoji_keywords, all_words, spreadsheet

def save_log(spreadsheet, input_text, candidate_emojis, matched_words_str, selected_emoji):
    """収集データシートにログを保存 (選択された絵文字を記録)"""
    save_sheet_name = "収集データ"
    try:
        try:
            log_sheet = spreadsheet.worksheet(save_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            log_sheet = spreadsheet.add_worksheet(title=save_sheet_name, rows=1000, cols=5)
            # ヘッダーに「選択された絵文字」を追加
            log_sheet.append_row(["タイムスタンプ", "入力テキスト", "推薦候補リスト", "検出された単語", "選択された絵文字"])
        
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        # 候補リストを文字列化
        candidates_str = ", ".join(candidate_emojis)
        
        log_sheet.append_row([timestamp, input_text, candidates_str, matched_words_str, selected_emoji])
        return True, "保存完了"
    except Exception as e:
        return False, str(e)

# --- メインUI ---

def main():
    st.set_page_config(page_title="絵文字推薦システム", page_icon="🧐")
    
    st.title("🧐 絵文字推薦システム")
    st.markdown("文章を入力すると、単語の出現順に関連する絵文字を表示します。")

    # サイドバー
    with st.sidebar:
        st.header("ステータス")
        if SPREADSHEET_ID == 'ここにスプレッドシートIDを入力してください':
            st.error("⚠️ スプレッドシートIDを設定してください")
            st.stop()
        
        # データのロード（初回のみ）
        if 'data_loaded' not in st.session_state:
            with st.spinner("辞書データを構築中..."):
                try:
                    emoji_keywords, all_words, spreadsheet = load_data()
                    st.session_state['emoji_keywords'] = emoji_keywords
                    st.session_state['all_words'] = all_words
                    st.session_state['spreadsheet'] = spreadsheet
                    st.session_state['data_loaded'] = True
                    st.success("読込完了")
                except Exception as e:
                    st.error(f"エラー: {e}")
                    st.stop()
        else:
            st.success("データ準備OK")

    # 入力フォーム
    input_text = st.text_area("文章を入力してください", height=100, placeholder="例：猫が可愛くて最高に幸せ")

    # 「分析開始」ボタン
    if st.button("絵文字を検索する", type="primary"):
        if not input_text:
            st.warning("文章を入力してください。")
        else:
            emoji_keywords = st.session_state['emoji_keywords']
            all_words = st.session_state['all_words']

            # 1. 単語の出現順序を特定する
            # (入力文の中で、登録単語がどこに出現するかを検索)
            found_matches = [] # (index, word) のリスト
            
            for word in all_words:
                idx = input_text.find(word)
                if idx != -1:
                    # 単語が見つかったら、その位置(index)と一緒に記録
                    found_matches.append((idx, word))
            
            # 出現位置(index)順にソートする
            found_matches.sort(key=lambda x: x[0])
            
            # ソートされた単語リストを作成
            sorted_words = [m[1] for m in found_matches]
            matched_words_str = ", ".join(sorted_words) if sorted_words else "なし"

            # 2. 単語順に絵文字をリストアップ
            candidates = []
            seen_emojis = set()

            for word in sorted_words:
                # この単語を含む絵文字シートを探す
                for emoji, keywords in emoji_keywords.items():
                    if word in keywords:
                        if emoji not in seen_emojis:
                            candidates.append(emoji)
                            seen_emojis.add(emoji)
            
            # 結果をセッションステートに保存（ボタンを押しても消えないように）
            st.session_state['current_candidates'] = candidates
            st.session_state['current_text'] = input_text
            st.session_state['current_matched'] = matched_words_str
            
            # 完了メッセージをリセット
            if 'save_success' in st.session_state:
                del st.session_state['save_success']

    # 結果表示と選択エリア
    if 'current_candidates' in st.session_state:
        st.divider()
        st.subheader("👇 使いたい絵文字を選択してください")
        
        candidates = st.session_state['current_candidates']
        
        if not candidates:
            st.info("関連する絵文字が見つかりませんでした。")
        else:
            st.write(f"検出された単語順: {st.session_state['current_matched']}")
            
            # 絵文字をボタンとして並べる
            # 横に並べるカラム数
            cols = st.columns(6) 
            for i, emoji in enumerate(candidates):
                # 順繰りにカラムに入れていく
                with cols[i % 6]:
                    # ボタンが押されたらその絵文字を保存
                    if st.button(emoji, key=f"btn_{i}", use_container_width=True):
                        
                        spreadsheet = st.session_state['spreadsheet']
                        input_txt = st.session_state['current_text']
                        matched = st.session_state['current_matched']
                        
                        # 保存処理
                        with st.spinner(f"{emoji} を記録中..."):
                            success, msg = save_log(spreadsheet, input_txt, candidates, matched, emoji)
                            
                            if success:
                                st.session_state['save_success'] = f"✅ 「{emoji}」を選択・記録しました！"
                                # 選択後はリセットしたい場合は以下を有効化
                                # del st.session_state['current_candidates']
                                # st.rerun()
                            else:
                                st.error(f"保存エラー: {msg}")

        # 保存完了メッセージの表示
        if 'save_success' in st.session_state:
            st.success(st.session_state['save_success'])

if __name__ == "__main__":
    main()

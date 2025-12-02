import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import time
import pandas as pd
from janome.tokenizer import Tokenizer # 形態素解析用

# --- 設定項目 ---
# ローカルで動かす場合の鍵ファイル名
SERVICE_ACCOUNT_FILE = 'service_account.json'
# ★書き換えてください (スプレッドシートID)
SPREADSHEET_ID = '1P5Yx7tCPKIzicerO_9LlQBnupqdlDeKnKily2ZzVhYg' 

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
    """スプレッドシートから学習データを読み込む"""
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
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
    
    emoji_keywords = {}
    all_words = set()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_sheets = len(SHEET_NAMES)
    
    for i, sheet_name in enumerate(SHEET_NAMES):
        status_text.text(f"データを読み込み中... ({i+1}/{total_sheets}) {sheet_name}")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                rows = worksheet.get_all_values()
                
                keywords = set()
                start_row = 1 if rows and len(rows) > 0 and len(rows[0]) > 1 and '%' in str(rows[0][1]) else 0

                for row in rows[start_row:]:
                    for col_idx in [0, 2, 4]:
                        if len(row) > col_idx and row[col_idx]:
                            word = row[col_idx].strip()
                            if word:
                                keywords.add(word)
                                all_words.add(word)
                
                emoji_keywords[sheet_name] = keywords
                break
                
            except gspread.exceptions.WorksheetNotFound:
                break
            except gspread.exceptions.APIError as e:
                if "429" in str(e):
                    time.sleep((2 ** attempt) * 2)
                else:
                    break
            except Exception:
                break
        
        time.sleep(1.5)
        progress_bar.progress((i + 1) / total_sheets)

    status_text.empty()
    progress_bar.empty()
    
    return emoji_keywords, all_words, spreadsheet

# Tokenizerのロードをキャッシュ化
@st.cache_resource
def load_tokenizer():
    return Tokenizer()

def save_log(spreadsheet, input_text, candidate_emojis, matched_words_str, selected_emoji):
    """収集データシートにログを保存"""
    save_sheet_name = "収集データ"
    try:
        try:
            log_sheet = spreadsheet.worksheet(save_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            log_sheet = spreadsheet.add_worksheet(title=save_sheet_name, rows=1000, cols=5)
            log_sheet.append_row(["タイムスタンプ", "入力テキスト", "推薦候補リスト", "検出された単語", "選択された絵文字"])
        
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        candidates_str = ", ".join(candidate_emojis)
        
        log_sheet.append_row([timestamp, input_text, candidates_str, matched_words_str, selected_emoji])
        return True, "保存完了"
    except Exception as e:
        return False, str(e)

# --- コールバック関数 (ここが修正のポイント) ---
def on_emoji_click(selected_item):
    """絵文字ボタンが押されたときに実行される関数"""
    
    # 必要なデータをセッションステートから取得
    spreadsheet = st.session_state['spreadsheet']
    input_txt = st.session_state['input_text_val']
    matched = st.session_state['current_matched']
    candidates = st.session_state['current_candidates']
    
    # 記録処理 (コールバック内ではspinnerが効かないことがあるため削除していますが処理は行われます)
    success, msg = save_log(spreadsheet, input_txt, candidates, matched, selected_item)
    
    if success:
        # 1. 文章の末尾に絵文字を追加
        if selected_item != "なし":
            st.session_state['input_text_val'] += selected_item
        
        # 2. 候補リストを削除してリセット
        del st.session_state['current_candidates']
        
        # 3. 成功メッセージを設定
        st.session_state['save_success'] = f"✅ 「{selected_item}」を選択・記録しました！"
    else:
        st.session_state['save_error'] = f"保存エラー: {msg}"

# --- メインUI ---

def main():
    st.set_page_config(page_title="絵文字推薦システム", page_icon="🧐")
    
    st.title("🧐 絵文字推薦システム")
    st.markdown("文章を入力すると、単語の出現順に関連する絵文字を表示します。")

    with st.sidebar:
        st.header("ステータス")
        if SPREADSHEET_ID == 'ここにスプレッドシートIDを入力してください':
            st.error("⚠️ スプレッドシートIDを設定してください")
            st.stop()
        
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

    # --- 入力フォーム ---
    if 'input_text_val' not in st.session_state:
        st.session_state['input_text_val'] = ""

    input_text = st.text_area(
        "文章を入力してください", 
        height=100, 
        placeholder="例：猫が可愛くて最高に幸せ",
        key="input_text_val"
    )

    # 「絵文字を検索する」ボタン
    if st.button("絵文字を検索する", type="primary"):
        if not input_text:
            st.warning("文章を入力してください。")
        else:
            emoji_keywords = st.session_state['emoji_keywords']
            all_words = st.session_state['all_words']

            # Janomeによる形態素解析
            tokenizer = load_tokenizer()
            tokens = tokenizer.tokenize(input_text)
            
            sorted_words = []
            for token in tokens:
                word_base = token.base_form
                if word_base in all_words:
                    sorted_words.append(word_base)
            
            matched_words_str = ", ".join(sorted_words) if sorted_words else "なし"

            # 絵文字リストアップ
            candidates = []
            seen_emojis = set()
            for word in sorted_words:
                for emoji, keywords in emoji_keywords.items():
                    if word in keywords:
                        if emoji not in seen_emojis:
                            candidates.append(emoji)
                            seen_emojis.add(emoji)
            
            st.session_state['current_candidates'] = candidates
            st.session_state['current_matched'] = matched_words_str
            
            if 'save_success' in st.session_state:
                del st.session_state['save_success']
            if 'save_error' in st.session_state:
                del st.session_state['save_error']

    # 結果表示と選択エリア
    if 'current_candidates' in st.session_state:
        st.divider()
        
        candidates = st.session_state['current_candidates']
        display_candidates = candidates + ["なし"]
        
        if not candidates:
            st.info("※ 単語から推測できる絵文字が見つかりませんでした。")

        # 絵文字ボタンを並べる
        num_cols = 6
        cols = st.columns(num_cols) 
        
        for i, item in enumerate(display_candidates):
            with cols[i % num_cols]:
                # ★修正点: on_click を使用してコールバックを設定
                st.button(
                    item, 
                    key=f"btn_{i}", 
                    use_container_width=True,
                    on_click=on_emoji_click,  # クリック時に実行する関数
                    args=(item,)              # 関数に渡す引数（選ばれた絵文字）
                )

    # 保存結果メッセージの表示
    if 'save_success' in st.session_state:
        st.success(st.session_state['save_success'])
    if 'save_error' in st.session_state:
        st.error(st.session_state['save_error'])

if __name__ == "__main__":
    main()

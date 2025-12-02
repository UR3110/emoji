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

def parse_probability(prob_str):
    """確率文字列を数値に変換"""
    if not prob_str:
        return 0.0
    try:
        clean_str = str(prob_str).replace('%', '').replace(',', '').strip()
        return float(clean_str) / 100.0
    except ValueError:
        return 0.0

@st.cache_resource
def load_data():
    """スプレッドシートから学習データを読み込む (確率も含めて取得)"""
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 認証ロジック
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
    
    # {絵文字: {単語: 確率, ...}} の形式で保持
    emoji_probabilities = {}
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
                
                emoji_probs = {}
                start_row = 1 if rows and len(rows) > 0 and len(rows[0]) > 1 and '%' in str(rows[0][1]) else 0

                for row in rows[start_row:]:
                    # 名詞(0), 動詞(2), 形容詞(4) の列にある単語と確率を取得
                    for col_idx in [0, 2, 4]:
                        if len(row) > col_idx + 1 and row[col_idx] and row[col_idx+1]:
                            word = row[col_idx].strip()
                            prob = parse_probability(row[col_idx+1])
                            if word and prob > 0:
                                emoji_probs[word] = prob
                                all_words.add(word)
                
                emoji_probabilities[sheet_name] = emoji_probs
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
        
        time.sleep(1.5) # API制限回避
        progress_bar.progress((i + 1) / total_sheets)

    status_text.empty()
    progress_bar.empty()
    
    return emoji_probabilities, all_words, spreadsheet

def save_log(spreadsheet, input_text, candidate_emojis, matched_words_str, selected_emoji):
    """収集データシートにログを保存"""
    save_sheet_name = "収集データ"
    try:
        try:
            log_sheet = spreadsheet.worksheet(save_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            log_sheet = spreadsheet.add_worksheet(title=save_sheet_name, rows=1000, cols=5)
            # ヘッダー
            log_sheet.append_row(["タイムスタンプ", "入力テキスト", "推薦候補リスト(上位5つ)", "検出された単語", "選択された絵文字"])
        
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        # 候補リストを文字列化 (リスト型なら文字列へ変換)
        candidates_str = ", ".join(candidate_emojis) if isinstance(candidate_emojis, list) else str(candidate_emojis)
        
        log_sheet.append_row([timestamp, input_text, candidates_str, matched_words_str, selected_emoji])
        return True, "保存完了"
    except Exception as e:
        return False, str(e)

# --- メインUI ---

def main():
    st.set_page_config(page_title="絵文字推薦システム", page_icon="🧐")
    
    st.title("🧐 絵文字推薦システム")
    st.markdown("文章を入力すると、**関連度が高い順**に絵文字を推薦します。")

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
                    emoji_probabilities, all_words, spreadsheet = load_data()
                    st.session_state['emoji_probabilities'] = emoji_probabilities
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
    input_text = st.text_area("文章を入力してください", height=100, placeholder="例：今日はよく寝た")

    # 「絵文字を検索する」ボタン
    if st.button("絵文字を検索する", type="primary"):
        if not input_text:
            st.warning("文章を入力してください。")
        else:
            emoji_probabilities = st.session_state['emoji_probabilities']
            all_words = st.session_state['all_words']

            # 1. 単語マッチング
            found_words = [word for word in all_words if word in input_text]
            matched_words_str = ", ".join(found_words) if found_words else "なし"

            # 2. スコア計算 (確率の合計)
            scores = {}
            for emoji, word_probs in emoji_probabilities.items():
                score = 0.0
                for word in found_words:
                    if word in word_probs:
                        score += word_probs[word]
                scores[emoji] = score

            # 3. スコア順にソートして上位5つを取得
            # (スコアが0より大きいものに限る)
            sorted_emojis = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top5_candidates = [emoji for emoji, score in sorted_emojis if score > 0][:5]
            
            # 結果をセッションステートに保存
            st.session_state['current_candidates'] = top5_candidates
            st.session_state['current_text'] = input_text
            st.session_state['current_matched'] = matched_words_str
            
            # 完了メッセージをリセット
            if 'save_success' in st.session_state:
                del st.session_state['save_success']

    # 結果表示と選択エリア
    if 'current_candidates' in st.session_state:
        st.divider()
        # 以前のサブヘッダーやキャプション表示を削除しました
        
        candidates = st.session_state['current_candidates']
        
        # 候補リストに「なし」を追加して表示用リストを作る
        display_candidates = candidates + ["なし"]
        
        # 検出単語の表示を削除しました
        if not candidates:
            st.info("※ 単語から推測できる絵文字が見つかりませんでした。")

        # 絵文字ボタンを並べる
        # 最大6個（上位5つ + なし）なので6カラム
        cols = st.columns(6) 
        
        for i, item in enumerate(display_candidates):
            with cols[i]:
                # ボタンのラベル（"なし"の場合はそのまま、絵文字の場合は大きく表示）
                label = item
                
                # ボタンが押されたら保存処理へ
                if st.button(label, key=f"btn_{i}", use_container_width=True):
                    
                    spreadsheet = st.session_state['spreadsheet']
                    input_txt = st.session_state['current_text']
                    matched = st.session_state['current_matched']
                    # 記録するのは上位5つの候補リスト（"なし"は含めない）
                    candidates_to_log = candidates
                    
                    # 保存処理
                    with st.spinner(f"「{item}」を記録中..."):
                        success, msg = save_log(spreadsheet, input_txt, candidates_to_log, matched, item)
                        
                        if success:
                            # 完了メッセージの表示ロジックを削除しました
                            pass
                        else:
                            st.error(f"保存エラー: {msg}")

        # 完了メッセージの表示エリア自体を削除しました

if __name__ == "__main__":
    main()

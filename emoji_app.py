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
    """スプレッドシートから学習データを読み込む"""
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 認証ロジック: Secrets (Cloud) か JSONファイル (Local) かを自動判定
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    else:
        try:
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scope)
        except FileNotFoundError:
            st.error("認証ファイルが見つかりません。ローカルでは 'service_account.json' を配置するか、Streamlit CloudのSecretsを設定してください。")
            st.stop()

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    emoji_probabilities = {}
    all_words = set()
    
    # 進捗バーの表示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_sheets = len(SHEET_NAMES)
    
    for i, sheet_name in enumerate(SHEET_NAMES):
        status_text.text(f"データを読み込み中... ({i+1}/{total_sheets}) {sheet_name}")
        
        # ★★★ 429エラー (読み込み制限) 対策のリトライロジック ★★★
        max_retries = 5
        for attempt in range(max_retries):
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                rows = worksheet.get_all_values()
                
                emoji_probs = {}
                # ヘッダー判定（1行目の2列目に'%'が含まれていればヘッダーありとみなす）
                start_row = 1 if rows and len(rows) > 0 and len(rows[0]) > 1 and '%' in str(rows[0][1]) else 0

                for row in rows[start_row:]:
                    # 名詞(Col 0,1), 動詞(Col 2,3), 形容詞(Col 4,5)
                    for col_idx in [0, 2, 4]:
                        if len(row) > col_idx + 1 and row[col_idx] and row[col_idx+1]:
                            word = row[col_idx].strip()
                            prob = parse_probability(row[col_idx+1])
                            if prob > 0:
                                emoji_probs[word] = prob
                                all_words.add(word)
                
                emoji_probabilities[sheet_name] = emoji_probs
                break # 成功したらループを抜ける
                
            except gspread.exceptions.WorksheetNotFound:
                break # シートがない場合はスキップ
            except gspread.exceptions.APIError as e:
                # 429エラーなら待機して再試行
                if "429" in str(e):
                    wait_time = (2 ** attempt) * 2  # 2, 4, 8, 16...秒待機
                    time.sleep(wait_time)
                else:
                    print(f"Error loading {sheet_name}: {e}")
                    break
            except Exception as e:
                print(f"Unexpected error loading {sheet_name}: {e}")
                break
        
        # API制限回避のため、次のシート読み込みまで少し待機
        time.sleep(1.5)
        
        progress_bar.progress((i + 1) / total_sheets)

    status_text.empty()
    progress_bar.empty()
    
    return emoji_probabilities, all_words, spreadsheet

def save_log(spreadsheet, input_text, recommendations_data, matched_words_str):
    """収集データシートにログを保存"""
    save_sheet_name = "収集データ"
    try:
        try:
            log_sheet = spreadsheet.worksheet(save_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            log_sheet = spreadsheet.add_worksheet(title=save_sheet_name, rows=1000, cols=4)
            log_sheet.append_row(["タイムスタンプ", "入力テキスト", "推薦結果 (JSON)", "検出された単語"])
        
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        recommendations_json = json.dumps(recommendations_data, ensure_ascii=False)
        
        log_sheet.append_row([timestamp, input_text, recommendations_json, matched_words_str])
        return True, "保存完了"
    except Exception as e:
        return False, str(e)

# --- メインUI ---

def main():
    st.set_page_config(page_title="絵文字推薦システム", page_icon="🧐")
    
    st.title("🧐 絵文字推薦システム")
    st.markdown("文章を入力すると、Googleスプレッドシートのデータに基づいて最適な絵文字を推薦します。")

    with st.sidebar:
        st.header("ステータス")
        if SPREADSHEET_ID == 'ここにスプレッドシートIDを入力してください':
            st.error("⚠️ コード内のスプレッドシートIDを設定してください！")
            st.stop()
        
        if 'data_loaded' not in st.session_state:
            with st.spinner("データベースを構築中... (これには数分かかります)"):
                try:
                    emoji_probabilities, all_words, spreadsheet = load_data()
                    st.session_state['emoji_probabilities'] = emoji_probabilities
                    st.session_state['all_words'] = all_words
                    st.session_state['spreadsheet'] = spreadsheet
                    st.session_state['data_loaded'] = True
                    st.success(f"読込完了: {len(all_words)}語")
                except Exception as e:
                    st.error(f"データ読み込みエラー: {e}")
                    st.stop()
        else:
            st.success(f"データ準備OK ({len(st.session_state['all_words'])}語)")

    input_text = st.text_area("推薦したい文章を入力してください", height=100, placeholder="例：今日は天気が良くて最高に楽しい一日だった")

    if st.button("推薦する", type="primary"):
        if not input_text:
            st.warning("文章を入力してください。")
            return

        emoji_probabilities = st.session_state['emoji_probabilities']
        all_words = st.session_state['all_words']
        spreadsheet = st.session_state['spreadsheet']

        found_words = [word for word in all_words if word in input_text]
        matched_words_str = ", ".join(found_words) if found_words else "なし"

        with st.expander("検出された単語を見る"):
            st.write(matched_words_str)

        scores = {}
        for emoji, word_probs in emoji_probabilities.items():
            score = 0.0
            for word in found_words:
                if word in word_probs:
                    score += word_probs[word]
            scores[emoji] = score

        sorted_emojis = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top5 = sorted_emojis[:5]

        st.subheader("🏆 推薦結果")
        
        recommendations_data = []
        
        if not top5 or top5[0][1] == 0:
            st.info("マッチする絵文字が見つかりませんでした。")
        else:
            cols = st.columns(5)
            for idx, (emoji, score) in enumerate(top5):
                if score > 0:
                    with cols[idx]:
                        st.metric(label=f"{idx+1}位", value=emoji, delta=f"{score:.4f}")
                    recommendations_data.append({"rank": idx+1, "emoji": emoji, "score": score})

        with st.spinner("結果を保存中..."):
            success, msg = save_log(spreadsheet, input_text, recommendations_data, matched_words_str)
            if success:
                st.toast("✅ データをスプレッドシートに保存しました")
            else:
                st.error(f"保存エラー: {msg}")

if __name__ == "__main__":
    main()

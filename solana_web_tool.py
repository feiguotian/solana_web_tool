import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime
from io import BytesIO

API_KEY = "ccf35c43-496e-4514-b595-1039601450f2"
RPC_ENDPOINT = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

# 请求 RPC函数
def rpc_request(method, params):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    try:
        res = requests.post(RPC_ENDPOINT, json=payload, timeout=10)
        res.raise_for_status()
        data = res.json()
        if "result" in data:
            return data["result"], "success"
        elif "error" in data and "message" in data["error"]:
            msg = data["error"]["message"].lower()
            if "rate limit" in msg:
                return None, "rate_limited"
            elif "historical data" in msg:
                return None, "requires_payment"
            else:
                return None, "rpc_error"
        else:
            return None, "unknown_error"
    except Exception:
        return None, "network_error"

# 获取交易签名
def get_signatures(wallet):
    result, status = rpc_request("getSignaturesForAddress", [wallet, {"limit": 1000}])
    if result is None:
        return [], status
    return [tx["signature"] for tx in result], status

# 获取单条交易详情
def get_transaction_detail(signature):
    for _ in range(10):
        result, status = rpc_request("getTransaction", [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
        if status == "success":
            return result, "成功"
        elif status == "requires_payment":
            return None, "需要付费"
        elif status == "rate_limited":
            time.sleep(1)
            continue
        elif status == "rpc_error":
            return None, "链上无效交易"
        else:
            time.sleep(0.5)
    return None, "获取失败"

# 分析交易详情
def analyze_transactions(signatures, target_wallet, log_func):
    records = []
    total = len(signatures)
    for i, sig in enumerate(signatures):
        log_func(f"[{i+1}/{total}] 获取交易 {sig} ...")
        tx_data, status = get_transaction_detail(sig)
        if status != "成功":
            records.append({"交易签名": sig, "状态": status})
            continue

        block_time = tx_data.get("blockTime")
        time_str = datetime.fromtimestamp(block_time).strftime("%Y-%m-%d %H:%M:%S") if block_time else ""

        pre_balances = tx_data["meta"]["preBalances"]
        post_balances = tx_data["meta"]["postBalances"]
        accounts = tx_data["transaction"]["message"]["accountKeys"]

        if target_wallet in accounts:
            index = accounts.index(target_wallet)
            pre = pre_balances[index] / 1e9
            post = post_balances[index] / 1e9
            direction = "转入" if post > pre else "转出"
            amount = abs(post - pre)

            for j, acc in enumerate(accounts):
                if acc == target_wallet:
                    continue
                pre_j = pre_balances[j] / 1e9
                post_j = post_balances[j] / 1e9
                if (direction == "转入" and post_j < pre_j) or (direction == "转出" and post_j > pre_j):
                    records.append({
                        "交易签名": sig,
                        "时间": time_str,
                        "转入/转出": direction,
                        "金额(SOL)": amount,
                        "本地址余额": post,
                        "对方地址": acc,
                        "对方余额": post_j,
                        "状态": status
                    })
    return records

def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=False)
    writer.save()
    processed_data = output.getvalue()
    return processed_data

def main():
    st.title("Solana 钱包转账查询工具")

    wallet_input = st.text_input("请输入Solana钱包地址", "")
    if st.button("开始查询"):
        if not wallet_input:
            st.warning("请输入有效的钱包地址！")
            return
        status_text = st.empty()
        log_text = st.empty()
        logs = []

        def log_func(msg):
            logs.append(msg)
            log_text.text("\n".join(logs))

        status_text.text("⌛ 正在获取交易签名...")
        signatures, status = get_signatures(wallet_input)
        if status != "success":
            st.error(f"获取交易签名失败，原因：{status}")
            return
        if not signatures:
            st.warning("该钱包没有交易记录。")
            return
        status_text.text(f"✅ 获取到 {len(signatures)} 条交易记录，开始解析交易详情...")
        records = analyze_transactions(signatures, wallet_input, log_func)
        status_text.text(f"✅ 解析完成，共找到 {len(records)} 条转账记录。")

        if records:
            df = pd.DataFrame(records)
            st.dataframe(df)

            excel_bytes = to_excel(df)
            st.download_button(
                label="导出 Excel 表格",
                data=excel_bytes,
                file_name=f"{wallet_input}_sol转账明细.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("没有找到符合条件的转账记录。")

if __name__ == "__main__":
    main()

import requests
import time
import pandas as pd
from datetime import datetime
import streamlit as st

# 配置
API_KEY = "ccf35c43-496e-4514-b595-1039601450f2"
RPC_ENDPOINT = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

# RPC请求封装
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

# 获取交易签名列表
def get_signatures(wallet, log_func):
    log_func("🔍 正在获取交易记录...")
    result, status = rpc_request("getSignaturesForAddress", [wallet, {"limit": 1000}])
    if result is None:
        log_func(f"❌ 获取失败: {status}")
        return []
    log_func(f"✅ 获取到 {len(result)} 条交易记录")
    return [tx["signature"] for tx in result]

# 获取交易详情
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

# 分析交易
def analyze_transactions(signatures, wallet, log_func):
    records = []
    for i, sig in enumerate(signatures):
        log_func(f"[{i+1}/{len(signatures)}] 正在分析交易 {sig}...")
        tx_data, status = get_transaction_detail(sig)

        if status != "成功" or tx_data is None:
            records.append({"交易签名": sig, "状态": status})
            continue

        meta = tx_data.get("meta", {})
        block_time = tx_data.get("blockTime")
        time_str = datetime.fromtimestamp(block_time).strftime("%Y-%m-%d %H:%M:%S") if block_time else ""

        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])
        accounts = tx_data["transaction"]["message"]["accountKeys"]

        if wallet in accounts:
            index = accounts.index(wallet)
            pre = pre_balances[index] / 1e9
            post = post_balances[index] / 1e9
            direction = "转入" if post > pre else "转出"
            amount = abs(post - pre)

            # 查找对方地址
            for j, acc in enumerate(accounts):
                if acc == wallet:
                    continue
                pre_j = pre_balances[j] / 1e9
                post_j = post_balances[j] / 1e9
                if direction == "转入" and post_j < pre_j:
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
                elif direction == "转出" and post_j > pre_j:
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

# Streamlit 主函数
def main():
    st.set_page_config(page_title="Solana 钱包交易查询", layout="wide")
    st.title("📊 Solana 钱包交易转账查询工具")

    wallet_input = st.text_input("请输入 Solana 钱包地址（例如：4rToHJLjcdDjtuXupVqCXgMWBaJcxLtQ6dZVMZAsCUsq）")

    log_output = st.empty()
    result_table = st.empty()
    export_button = st.empty()

    logs = []

    def log(msg):
        logs.append(msg)
        log_output.code("\n".join(logs[-20:]))

    if st.button("🔍 开始查询") and wallet_input:
        logs.clear()
        log("开始查询交易记录...")
        signatures = get_signatures(wallet_input, log)
        if not signatures:
            log("未获取到交易记录，终止。")
            return
        records = analyze_transactions(signatures, wallet_input, log)
        df = pd.DataFrame(records)
        result_table.dataframe(df)

        # 导出 Excel
        filename = "solana_wallet_tx.xlsx"
        df.to_excel(filename, index=False)
        with open(filename, "rb") as f:
            export_button.download_button(
                label="📁 下载Excel文件",
                data=f,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main()

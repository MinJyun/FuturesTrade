# sj-trading

基於 Shioaji API 的 Python 交易實作框架。

## 專案目的

`sj-trading` 是一個模組化的交易應用程式，整合了 Shioaji API 用於股票與期貨交易。本專案採用關注點分離 (Separation of Concerns) 的設計原則，將報價管理、下單執行與交易策略模組化，並提供統一的 CLI 介面。

## 關鍵技術

- **Python 3.12+**
- **Shioaji**: 永豐金證券交易 API 串接。
- **Polars**: 高效能 DataFrame 資料處理（用於 Tick 儲存與 K 棒計算）。
- **uv**: Python 套件與虛擬環境管理工具。
- **Typer**: 命令列介面 (CLI) 實作。

## 專案結構

```text
src/sj_trading/
├── core/           # 核心模組：API 連線管理 (ShioajiClient) 與環境變數設定
├── data/           # 數據模組：報價訂閱與 Tick/K 棒處理 (QuoteManager)
├── trading/        # 交易模組：股票與期貨下單執行 (OrderManager)
├── strategy/       # 策略模組：交易邏輯實作 (例如 MA Crossover)
└── main.py         # 程式入口：整合各模組的 CLI 指令
```

## 快速開始

### 1. 安裝環境

本專案使用 `uv` 管理。請確保已安裝 `uv`。

```bash
uv sync
```

### 2. 設定環境變數

在專案根目錄建立 `.env` 檔案：

```env
API_KEY=your_api_key
SECRET_KEY=your_secret_key
CA_CERT_PATH=path_to_your_ca_cert
CA_PASSWORD=your_ca_password
```

### 3. 執行指令

切換到專案目錄：

```bash
cd sj-trading
```

#### 查看版本

```bash
uv run sj-trading version
```

#### 訂閱即時報價 (以台指期 TMFR1 為例)

```bash
uv run sj-trading quote TMFR1
```

#### 執行交易策略 (以 5MA 突破策略為例)

```bash
uv run sj-trading trade --strategy ma --symbol TMFR1
```

#### 測試下單 (模擬環境)

```bash
uv run sj-trading test-order --type future
```

## 開發指南

- **新增策略**：繼承 `src/sj_trading/strategy/base.py:BaseStrategy` 並實作 `run` 與 `stop`。
- **新增 CLI 指令**：在 `src/sj_trading/main.py` 中新增 `@app.command()`。

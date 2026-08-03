# SPU 财务 BI 初稿

页面左侧提供 2025、2026 原始经营报表导入入口；未上传的年度会继续使用默认路径。
也可以使用环境变量 `FINANCE_BI_2025_PATH` 与 `FINANCE_BI_2026_PATH` 覆盖默认路径。

```bash
python3 -m streamlit run FinanceBI.py
```

看板按 SPU 聚合，SKU/MSKU 只保留在导入映射层，不在页面、筛选和导出中显示。
毛利额和毛利率统一使用“毛利额-1”口径，库存相关成本以“库存折损”展示。

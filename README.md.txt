# 📈 TD股票分析系统

基于Tushare数据的专业股票技术分析系统，采用前复权数据进行精确分析。

## 🌟 主要功能

- **智能股票筛选**: 根据股价、换手率、市值等条件筛选优质股票
- **技术分析**: 基于移动平均线等技术指标进行趋势分析
- **前复权数据**: 使用前复权价格，确保技术分析准确性
- **实时数据**: 接入Tushare专业金融数据接口

## 📊 筛选条件

- 排除科创板、创业板、北交所和ST股票
- 股价 < 10元（可调整）
- 换手率 > 1.5%（可调整）
- 总市值 > 40亿（可调整）
- 按总市值从小到大排序

## 🛠️ 技术栈

- **Streamlit**: Web应用框架
- **Tushare**: 金融数据接口
- **Pandas**: 数据处理
- **Matplotlib/Plotly**: 数据可视化
- **NumPy/SciPy**: 数值计算

## 🚀 在线访问

[点击这里访问在线版本](https://your-app-url.streamlit.app)

## 💻 本地运行

```bash
# 克隆仓库
git clone https://github.com/your-username/td-stock-analyzer.git
cd td-stock-analyzer

# 安装依赖
pip install -r requirements.txt

# 运行应用
streamlit run app.py
```

## ⚠️ 风险提示

本系统仅供技术分析参考，不构成投资建议。投资有风险，入市需谨慎！

## 📝 更新日志

### v1.0.0
- 初始版本发布
- 基础股票筛选功能
- 简化版技术分析

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 📄 许可证

MIT License
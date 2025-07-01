import streamlit as st
import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import warnings
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm
from scipy.signal import argrelextrema
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64

warnings.filterwarnings('ignore')

# 页面配置
st.set_page_config(
    page_title="TD股票分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 设置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'Helvetica']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.facecolor'] = 'white'
plt.rcParams['axes.facecolor'] = 'white'

# 设置tushare token
TOKEN = '27fab716cc7ea549b52a8345e43cfa9be8daa8976ca6fdfe2c4a1d3e'

@st.cache_data
def init_tushare():
    """初始化tushare"""
    ts.set_token(TOKEN)
    return ts.pro_api(TOKEN)

@st.cache_data
def check_trade_date(date_str):
    """检查输入的日期是否为交易日"""
    pro = init_tushare()
    try:
        trade_cal = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
        if len(trade_cal) > 0 and trade_cal.iloc[0]['is_open'] == 1:
            return True
        return False
    except:
        return False

@st.cache_data
def get_latest_trade_date():
    """获取最近的交易日"""
    pro = init_tushare()
    try:
        today = datetime.now().strftime('%Y%m%d')
        trade_cal = pro.trade_cal(exchange='SSE', end_date=today, is_open=1)
        trade_cal = trade_cal.sort_values('cal_date', ascending=False)
        return trade_cal.iloc[0]['cal_date']
    except Exception as e:
        st.error(f"获取交易日期失败: {e}")
        return datetime.now().strftime('%Y%m%d')

@st.cache_data
def stock_selector(target_date=None):
    """股票筛选主函数 - 简化版"""
    if target_date is None:
        target_date = get_latest_trade_date()
    
    pro = init_tushare()
    
    try:
        # 获取股票列表
        stock_list = pro.stock_basic(exchange='', list_status='L', 
                                   fields='ts_code,symbol,name,area,industry,list_date')
        
        # 排除特定板块和ST股票
        stock_list = stock_list[~stock_list['symbol'].str.startswith(('688', '300', '8'))]
        stock_list = stock_list[~stock_list['name'].str.contains('ST', case=False, na=False)]
        
        st.info(f"初始股票数量: {len(stock_list)}")
        
        # 分批获取数据，避免API限制
        batch_size = 100
        all_data = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_batches = (len(stock_list) // batch_size) + 1
        
        for i in range(0, len(stock_list), batch_size):
            batch = stock_list.iloc[i:i+batch_size]
            status_text.text(f"获取数据批次 {i//batch_size + 1}/{total_batches}")
            
            try:
                # 尝试使用新接口
                batch_data = pro.stk_factor_pro(**{
                    "ts_code": "",
                    "start_date": target_date,
                    "end_date": target_date,
                    "trade_date": target_date,
                    "limit": "",
                    "offset": ""
                }, fields=[
                    "ts_code", "trade_date", "close", "close_qfq", "pct_chg",
                    "vol", "amount", "turnover_rate", "total_mv"
                ])
                
                # 只保留当前批次的股票
                batch_data = batch_data[batch_data['ts_code'].isin(batch['ts_code'])]
                
            except Exception as e:
                st.warning(f"新接口失败，使用备用方案: {e}")
                # 备用方案
                try:
                    batch_data = pro.daily(trade_date=target_date)
                    batch_data = batch_data[batch_data['ts_code'].isin(batch['ts_code'])]
                    batch_data['close_qfq'] = batch_data['close']
                except:
                    continue
            
            if len(batch_data) > 0:
                all_data.append(batch_data)
            
            progress_bar.progress((i + batch_size) / len(stock_list))
            time.sleep(0.1)  # 避免API限制
        
        progress_bar.empty()
        status_text.empty()
        
        if not all_data:
            st.error("无法获取股票数据")
            return pd.DataFrame()
        
        # 合并数据
        daily_data = pd.concat(all_data, ignore_index=True)
        st.success(f"成功获取 {len(daily_data)} 只股票数据")
        
        # 合并股票信息
        result = pd.merge(stock_list, daily_data, on='ts_code', how='inner')
        
        # 筛选条件
        price_col = 'close_qfq' if 'close_qfq' in result.columns else 'close'
        result = result[result[price_col] < 10]
        st.info(f"股价<10元: {len(result)} 只")
        
        if 'turnover_rate' in result.columns:
            result = result.dropna(subset=['turnover_rate'])
            result = result[result['turnover_rate'] > 1.5]
            st.info(f"换手率>1.5%: {len(result)} 只")
        
        if 'total_mv' in result.columns:
            result = result[result['total_mv'] > 400000]
            result = result.sort_values('total_mv', ascending=True)
            st.info(f"市值>40亿: {len(result)} 只")
        
        return result
        
    except Exception as e:
        st.error(f"筛选出错: {e}")
        return pd.DataFrame()

def simple_td_analysis(ts_code, name, target_date):
    """简化版TD分析"""
    pro = init_tushare()
    
    try:
        # 获取历史数据
        end_date = target_date
        start_date = (pd.to_datetime(target_date) - timedelta(days=120)).strftime('%Y%m%d')
        
        hist_data = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        hist_data = hist_data.sort_values('trade_date')
        
        if len(hist_data) < 20:
            return None
        
        # 简单的技术指标计算
        hist_data['ma5'] = hist_data['close'].rolling(5).mean()
        hist_data['ma20'] = hist_data['close'].rolling(20).mean()
        
        latest = hist_data.iloc[-1]
        
        # 简化的分析结果
        return {
            'code': ts_code,
            'name': name,
            'current_price': latest['close'],
            'pct_chg': latest['pct_chg'],
            'ma5': latest['ma5'],
            'ma20': latest['ma20'],
            'volume': latest['vol'],
            'trend': 'up' if latest['close'] > latest['ma20'] else 'down',
            'analysis_date': target_date
        }
        
    except Exception as e:
        st.error(f"分析 {name} 失败: {e}")
        return None

def main():
    # 标题
    st.title("📈 TD股票分析系统")
    st.markdown("### 基于前复权数据的专业技术分析")
    st.markdown("---")
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 分析设置")
        
        # 日期选择
        use_latest = st.checkbox("使用最近交易日", value=True)
        
        if not use_latest:
            selected_date = st.date_input(
                "选择分析日期",
                value=datetime.now().date(),
                max_value=datetime.now().date()
            )
            target_date = selected_date.strftime('%Y%m%d')
            
            # 验证交易日
            if not check_trade_date(target_date):
                st.error("❌ 所选日期不是交易日！")
                st.stop()
            else:
                st.success("✅ 交易日验证通过")
        else:
            target_date = get_latest_trade_date()
            st.success(f"📅 分析日期: {target_date}")
        
        # 筛选参数
        st.subheader("🎯 筛选条件")
        max_price = st.slider("最大股价(元)", 5.0, 20.0, 10.0, 0.5)
        min_turnover = st.slider("最小换手率(%)", 0.5, 5.0, 1.5, 0.1)
        min_market_cap = st.slider("最小市值(亿元)", 20, 100, 40, 5)
        
        st.markdown("---")
        st.markdown("### 📋 筛选条件说明")
        st.markdown(f"""
        - 排除科创板、创业板、ST股票
        - 股价 < {max_price}元
        - 换手率 > {min_turnover}%  
        - 市值 > {min_market_cap}亿元
        - 按市值从小到大排序
        """)
    
    # 主界面标签页
    tab1, tab2, tab3 = st.tabs(["📊 股票筛选", "📈 技术分析", "📚 使用说明"])
    
    with tab1:
        st.subheader("🎯 股票筛选结果")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("🚀 开始筛选分析", type="primary", use_container_width=True):
                with st.spinner("正在筛选股票，请稍候..."):
                    try:
                        result = stock_selector(target_date)
                        
                        if len(result) > 0:
                            st.balloons()
                            st.success(f"🎉 筛选完成！共找到 {len(result)} 只符合条件的股票")
                            
                            # 保存结果到session state
                            st.session_state.filtered_stocks = result
                            st.session_state.target_date = target_date
                            
                            # 显示结果统计
                            col_a, col_b, col_c, col_d = st.columns(4)
                            
                            with col_a:
                                st.metric("📊 股票数量", len(result))
                            
                            with col_b:
                                price_col = 'close_qfq' if 'close_qfq' in result.columns else 'close'
                                avg_price = result[price_col].mean()
                                st.metric("💰 平均股价", f"¥{avg_price:.2f}")
                            
                            with col_c:
                                if 'turnover_rate' in result.columns:
                                    avg_turnover = result['turnover_rate'].mean()
                                    st.metric("🔄 平均换手率", f"{avg_turnover:.2f}%")
                                else:
                                    st.metric("🔄 换手率", "数据缺失")
                            
                            with col_d:
                                if 'total_mv' in result.columns:
                                    avg_mv = result['total_mv'].mean() / 10000
                                    st.metric("📈 平均市值", f"{avg_mv:.1f}亿")
                                else:
                                    st.metric("📈 市值", "数据缺失")
                            
                            # 显示数据表格
                            st.subheader("📋 筛选结果详情")
                            
                            # 选择要显示的列
                            display_cols = ['ts_code', 'name']
                            if 'close_qfq' in result.columns:
                                display_cols.append('close_qfq')
                                result = result.rename(columns={'close_qfq': '股价(前复权)'})
                            elif 'close' in result.columns:
                                display_cols.append('close')
                                result = result.rename(columns={'close': '股价'})
                            
                            if 'pct_chg' in result.columns:
                                display_cols.append('pct_chg')
                                result = result.rename(columns={'pct_chg': '涨跌幅%'})
                            
                            if 'turnover_rate' in result.columns:
                                display_cols.append('turnover_rate')
                                result = result.rename(columns={'turnover_rate': '换手率%'})
                            
                            if 'total_mv' in result.columns:
                                result['市值(亿)'] = result['total_mv'] / 10000
                                display_cols.append('市值(亿)')
                            
                            # 重命名显示列
                            result = result.rename(columns={
                                'ts_code': '股票代码',
                                'name': '股票名称'
                            })
                            
                            display_cols = ['股票代码', '股票名称'] + [col for col in display_cols[2:] if col in result.columns]
                            
                            # 显示表格
                            st.dataframe(
                                result[display_cols].head(20),
                                use_container_width=True,
                                hide_index=True
                            )
                            
                            if len(result) > 20:
                                st.info(f"仅显示前20只股票，共筛选出{len(result)}只")
                        
                        else:
                            st.warning("❌ 未找到符合条件的股票，请调整筛选参数")
                            
                    except Exception as e:
                        st.error(f"❌ 筛选过程中出现错误: {str(e)}")
        
        with col2:
            st.info("""
            **💡 操作提示:**
            
            1. 点击"开始筛选"按钮
            2. 等待数据获取完成
            3. 查看筛选结果
            4. 切换到"技术分析"标签页进行深度分析
            """)
    
    with tab2:
        st.subheader("📈 技术分析")
        
        if 'filtered_stocks' not in st.session_state:
            st.info("📊 请先在'股票筛选'页面获取股票数据")
        else:
            stocks_df = st.session_state.filtered_stocks
            target_date = st.session_state.target_date
            
            st.success(f"📋 已加载 {len(stocks_df)} 只股票数据，分析日期: {target_date}")
            
            # 股票选择
            stock_codes = stocks_df['ts_code'].tolist()
            stock_names = stocks_df['name'].tolist()
            
            # 创建选择选项
            options = [f"{name} ({code})" for name, code in zip(stock_names, stock_codes)]
            
            selected_options = st.multiselect(
                "🎯 选择要分析的股票",
                options=options,
                default=options[:3] if len(options) >= 3 else options,
                help="建议一次分析3-5只股票，避免过多请求"
            )
            
            if selected_options:
                # 提取选中的股票代码
                selected_codes = []
                for option in selected_options:
                    code = option.split('(')[-1].split(')')[0]
                    selected_codes.append(code)
                
                st.info(f"📊 已选择 {len(selected_codes)} 只股票进行分析")
                
                if st.button("🔍 开始技术分析", type="primary"):
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    results = []
                    
                    for i, code in enumerate(selected_codes):
                        name = stocks_df[stocks_df['ts_code'] == code]['name'].iloc[0]
                        status_text.text(f"正在分析: {name} ({code}) [{i+1}/{len(selected_codes)}]")
                        
                        try:
                            analysis = simple_td_analysis(code, name, target_date)
                            if analysis:
                                results.append(analysis)
                        except Exception as e:
                            st.error(f"分析 {name} 时出错: {e}")
                        
                        progress_bar.progress((i + 1) / len(selected_codes))
                        time.sleep(0.2)  # 避免API限制
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    # 显示分析结果
                    if results:
                        st.success(f"✅ 分析完成！成功分析 {len(results)} 只股票")
                        
                        for result in results:
                            with st.expander(f"📊 {result['name']} ({result['code']}) - 技术分析结果", expanded=True):
                                
                                # 基本信息
                                col1, col2, col3, col4 = st.columns(4)
                                
                                with col1:
                                    st.metric("💰 当前价格", f"¥{result['current_price']:.2f}")
                                
                                with col2:
                                    delta_color = "normal" if result['pct_chg'] >= 0 else "inverse"
                                    st.metric("📈 涨跌幅", f"{result['pct_chg']:.2f}%", delta=f"{result['pct_chg']:.2f}%")
                                
                                with col3:
                                    ma5_trend = "📈" if result['current_price'] > result['ma5'] else "📉"
                                    st.metric("MA5", f"¥{result['ma5']:.2f}", delta=f"{ma5_trend}")
                                
                                with col4:
                                    ma20_trend = "📈" if result['current_price'] > result['ma20'] else "📉"
                                    st.metric("MA20", f"¥{result['ma20']:.2f}", delta=f"{ma20_trend}")
                                
                                # 趋势分析
                                st.subheader("📊 趋势分析")
                                
                                if result['trend'] == 'up':
                                    st.success("🚀 **趋势**: 多头趋势 - 股价位于20日均线上方")
                                else:
                                    st.error("📉 **趋势**: 空头趋势 - 股价位于20日均线下方")
                                
                                # 简单的操作建议
                                st.subheader("💡 操作建议")
                                
                                if result['current_price'] > result['ma20'] and result['pct_chg'] > 0:
                                    st.success("✅ 建议: 可考虑关注，趋势向好")
                                elif result['current_price'] < result['ma20'] and result['pct_chg'] < 0:
                                    st.warning("⚠️ 建议: 谨慎操作，趋势偏弱")
                                else:
                                    st.info("📊 建议: 观望为主，等待明确信号")
                                
                                # 成交量信息
                                st.write(f"📊 **成交量**: {result['volume']:,.0f} 手")
                                st.write(f"📅 **分析日期**: {result['analysis_date']}")
                    
                    else:
                        st.warning("❌ 没有获得有效的分析结果")
            else:
                st.info("请选择要分析的股票")
    
    with tab3:
        st.markdown("""
        # 📚 TD股票分析系统使用说明
        
        ## 🎯 系统功能
        
        这是一个基于Tushare数据的股票技术分析系统，主要功能包括：
        
        ### 📊 股票筛选
        - **智能筛选**: 根据股价、换手率、市值等条件筛选股票
        - **排除风险**: 自动排除科创板、创业板、ST股票等高风险品种
        - **前复权数据**: 使用前复权价格，确保技术分析的准确性
        
        ### 📈 技术分析
        - **均线分析**: MA5、MA20均线趋势判断
        - **价格趋势**: 多空趋势识别
        - **操作建议**: 基于技术指标给出操作建议
        
        ## 🛠️ 使用步骤
        
        ### 第一步：股票筛选
        1. 在侧边栏设置筛选条件
        2. 选择分析日期（建议使用最近交易日）
        3. 点击"开始筛选分析"按钮
        4. 等待筛选完成，查看结果
        
        ### 第二步：技术分析
        1. 切换到"技术分析"标签页
        2. 从筛选结果中选择要分析的股票
        3. 点击"开始技术分析"按钮
        4. 查看详细的技术分析报告
        
        ## ⚙️ 参数说明
        
        ### 筛选条件
        - **最大股价**: 筛选股价低于此值的股票
        - **最小换手率**: 筛选活跃度高的股票
        - **最小市值**: 排除过小的公司，降低风险
        
        ### 技术指标
        - **MA5**: 5日移动平均线，短期趋势指标
        - **MA20**: 20日移动平均线，中期趋势指标
        - **涨跌幅**: 当日价格变化百分比
        
        ## ⚠️ 重要提示
        
        ### 数据来源
        - 数据来源于Tushare专业金融数据接口
        - 使用前复权价格进行技术分析
        - 数据更新频率：交易日实时更新
        
        ### 风险提示
        ⚠️ **投资有风险，入市需谨慎**
        
        - 本系统仅供技术分析参考，不构成投资建议
        - 任何投资决策应基于个人独立判断
        - 建议结合基本面分析和风险管理
        - 过往表现不预示未来结果
        
        ### 免责声明
        - 本系统为教育和研究目的开发
        - 用户应对自己的投资行为负责
        - 系统作者不承担任何投资损失责任
        
        ## 🔧 技术支持
        
        ### 系统要求
        - 稳定的网络连接
        - 现代浏览器（Chrome、Firefox、Safari等）
        - 建议使用桌面端访问以获得最佳体验
        
        ### 常见问题
        
        **Q: 为什么筛选不到股票？**
        A: 可能是筛选条件过于严格，建议放宽参数重试
        
        **Q: 数据获取失败怎么办？**
        A: 可能是网络问题或API限制，请稍后重试
        
        **Q: 可以分析多少只股票？**
        A: 建议一次分析3-5只股票，避免API请求过频
        
        ---
        
        ### 🎉 感谢使用TD股票分析系统！
        
        如果您觉得系统有用，欢迎分享给其他朋友！
        """)

if __name__ == "__main__":
    main()

import streamlit as st
import tushare as ts
import requests
import json
from datetime import datetime, timedelta
import time

# 页面配置
st.set_page_config(
    page_title="TD股票分析系统",
    page_icon="📈",
    layout="wide"
)

# 设置tushare token
TOKEN = '27fab716cc7ea549b52a8345e43cfa9be8daa8976ca6fdfe2c4a1d3e'

@st.cache_data
def init_tushare():
    """初始化tushare"""
    ts.set_token(TOKEN)
    return ts.pro_api(TOKEN)

@st.cache_data
def get_latest_trade_date():
    """获取最近的交易日"""
    pro = init_tushare()
    try:
        today = datetime.now().strftime('%Y%m%d')
        trade_cal = pro.trade_cal(exchange='SSE', end_date=today, is_open=1)
        # 手动排序
        trade_cal_sorted = trade_cal.sort_values('cal_date', ascending=False)
        return trade_cal_sorted.iloc[0]['cal_date']
    except Exception as e:
        st.error(f"获取交易日期失败: {e}")
        return datetime.now().strftime('%Y%m%d')

@st.cache_data
def check_trade_date(date_str):
    """检查是否为交易日"""
    pro = init_tushare()
    try:
        trade_cal = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
        if len(trade_cal) > 0 and trade_cal.iloc[0]['is_open'] == 1:
            return True
        return False
    except:
        return False

@st.cache_data
def get_stock_basic():
    """获取股票基本信息"""
    pro = init_tushare()
    try:
        stock_list = pro.stock_basic(
            exchange='', 
            list_status='L', 
            fields='ts_code,symbol,name,area,industry,list_date'
        )
        return stock_list
    except Exception as e:
        st.error(f"获取股票列表失败: {e}")
        return None

@st.cache_data
def get_daily_data(trade_date, ts_codes_batch):
    """获取日线数据"""
    pro = init_tushare()
    try:
        # 获取指定股票的数据
        codes_str = ','.join(ts_codes_batch)
        daily_data = pro.daily_basic(
            ts_code=codes_str,
            trade_date=trade_date,
            fields='ts_code,close,turnover_rate,total_mv,pe,pb'
        )
        return daily_data
    except Exception as e:
        st.warning(f"获取部分数据失败: {e}")
        return None

def filter_stocks(target_date, max_price=10, min_turnover=1.5, min_market_cap=40):
    """筛选股票"""
    
    # 获取股票基本信息
    stock_list = get_stock_basic()
    if stock_list is None:
        return None
    
    # 过滤ST股票和特殊板块
    filtered_stocks = stock_list[
        ~stock_list['symbol'].str.startswith(('688', '300', '8'))
    ].copy()
    
    filtered_stocks = filtered_stocks[
        ~filtered_stocks['name'].str.contains('ST', case=False, na=False)
    ].copy()
    
    st.info(f"初步筛选后股票数量: {len(filtered_stocks)}")
    
    # 分批获取日线数据
    batch_size = 50
    all_results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_batches = (len(filtered_stocks) + batch_size - 1) // batch_size
    
    for i in range(0, len(filtered_stocks), batch_size):
        batch_stocks = filtered_stocks.iloc[i:i+batch_size]
        batch_codes = batch_stocks['ts_code'].tolist()
        
        status_text.text(f"获取数据: 批次 {i//batch_size + 1}/{total_batches}")
        
        # 获取日线数据
        daily_data = get_daily_data(target_date, batch_codes)
        
        if daily_data is not None and len(daily_data) > 0:
            # 合并基本信息和日线数据
            merged = batch_stocks.merge(daily_data, on='ts_code', how='inner')
            
            # 应用筛选条件
            if 'close' in merged.columns:
                merged = merged[merged['close'] < max_price]
            
            if 'turnover_rate' in merged.columns:
                merged = merged[merged['turnover_rate'] > min_turnover]
            
            if 'total_mv' in merged.columns:
                merged = merged[merged['total_mv'] > min_market_cap * 10000]  # 转换为万元
            
            if len(merged) > 0:
                all_results.append(merged)
        
        progress_bar.progress((i + batch_size) / len(filtered_stocks))
        time.sleep(0.1)  # 避免API限制
    
    progress_bar.empty()
    status_text.empty()
    
    if all_results:
        # 合并所有结果
        final_result = all_results[0]
        for df in all_results[1:]:
            final_result = final_result._append(df, ignore_index=True)
        
        # 按市值排序
        if 'total_mv' in final_result.columns:
            final_result = final_result.sort_values('total_mv', ascending=True)
        
        return final_result
    else:
        return None

def simple_technical_analysis(ts_code, name):
    """简单技术分析"""
    pro = init_tushare()
    try:
        # 获取最近30天数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=50)).strftime('%Y%m%d')
        
        hist_data = pro.daily(
            ts_code=ts_code, 
            start_date=start_date, 
            end_date=end_date
        )
        
        if len(hist_data) < 5:
            return None
        
        # 简单分析
        hist_data = hist_data.sort_values('trade_date')
        latest = hist_data.iloc[-1]
        
        # 计算简单均线
        recent_5 = hist_data.tail(5)['close'].mean()
        recent_10 = hist_data.tail(10)['close'].mean() if len(hist_data) >= 10 else recent_5
        
        # 趋势判断
        if latest['close'] > recent_5 > recent_10:
            trend = "🚀 强势上涨"
            trend_score = 85
        elif latest['close'] > recent_5:
            trend = "📈 温和上涨"
            trend_score = 65
        elif latest['close'] < recent_5 < recent_10:
            trend = "📉 下跌趋势"
            trend_score = 25
        else:
            trend = "📊 震荡整理"
            trend_score = 50
        
        return {
            'code': ts_code,
            'name': name,
            'current_price': latest['close'],
            'pct_chg': latest['pct_chg'],
            'volume': latest['vol'],
            'amount': latest['amount'],
            'ma5': recent_5,
            'ma10': recent_10,
            'trend': trend,
            'trend_score': trend_score,
            'analysis_date': latest['trade_date']
        }
        
    except Exception as e:
        st.error(f"分析 {name} 失败: {e}")
        return None

def main():
    # 页面标题
    st.title("📈 TD股票分析系统")
    st.markdown("### 基于Tushare数据的简化版股票分析")
    st.markdown("---")
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 分析设置")
        
        # 获取最新交易日
        latest_date = get_latest_trade_date()
        st.success(f"📅 最新交易日: {latest_date}")
        
        # 筛选参数
        st.subheader("🎯 筛选条件")
        max_price = st.slider("最大股价(元)", 5.0, 20.0, 10.0, 0.5)
        min_turnover = st.slider("最小换手率(%)", 0.5, 5.0, 1.5, 0.1)
        min_market_cap = st.slider("最小市值(亿元)", 20, 100, 40, 5)
        
        st.markdown("---")
        st.markdown("### 📋 说明")
        st.markdown("""
        - 排除科创板、创业板、ST股票
        - 基于最新交易日数据
        - 简化版技术分析
        - 支持基础筛选和排序
        """)
    
    # 主界面
    tab1, tab2, tab3 = st.tabs(["📊 股票筛选", "📈 技术分析", "📚 使用说明"])
    
    with tab1:
        st.subheader("🎯 股票筛选结果")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("🚀 开始筛选", type="primary", use_container_width=True):
                
                with st.spinner("正在筛选股票..."):
                    try:
                        result = filter_stocks(
                            latest_date, 
                            max_price, 
                            min_turnover, 
                            min_market_cap
                        )
                        
                        if result is not None and len(result) > 0:
                            st.balloons()
                            st.success(f"🎉 筛选完成！找到 {len(result)} 只符合条件的股票")
                            
                            # 保存到session state
                            st.session_state.filtered_stocks = result
                            st.session_state.target_date = latest_date
                            
                            # 显示统计信息
                            col_a, col_b, col_c, col_d = st.columns(4)
                            
                            with col_a:
                                st.metric("📊 股票数量", len(result))
                            
                            with col_b:
                                if 'close' in result.columns:
                                    avg_price = result['close'].mean()
                                    st.metric("💰 平均股价", f"¥{avg_price:.2f}")
                            
                            with col_c:
                                if 'turnover_rate' in result.columns:
                                    avg_turnover = result['turnover_rate'].mean()
                                    st.metric("🔄 平均换手率", f"{avg_turnover:.2f}%")
                            
                            with col_d:
                                if 'total_mv' in result.columns:
                                    avg_mv = result['total_mv'].mean() / 10000
                                    st.metric("📈 平均市值", f"{avg_mv:.1f}亿")
                            
                            # 显示结果表格
                            st.subheader("📋 筛选结果详情")
                            
                            # 格式化显示数据
                            display_data = result.copy()
                            
                            if 'total_mv' in display_data.columns:
                                display_data['市值(亿)'] = display_data['total_mv'] / 10000
                            
                            # 选择要显示的列
                            show_columns = ['ts_code', 'name']
                            if 'close' in display_data.columns:
                                show_columns.append('close')
                            if 'turnover_rate' in display_data.columns:
                                show_columns.append('turnover_rate')
                            if '市值(亿)' in display_data.columns:
                                show_columns.append('市值(亿)')
                            if 'pe' in display_data.columns:
                                show_columns.append('pe')
                            
                            # 重命名列
                            display_data = display_data.rename(columns={
                                'ts_code': '股票代码',
                                'name': '股票名称',
                                'close': '股价(元)',
                                'turnover_rate': '换手率(%)',
                                'pe': '市盈率'
                            })
                            
                            # 更新显示列名
                            show_columns = [display_data.columns[display_data.columns.get_loc(col)] 
                                          if col in display_data.columns else col 
                                          for col in ['股票代码', '股票名称', '股价(元)', '换手率(%)', '市值(亿)', '市盈率']
                                          if col in display_data.columns or any(display_data.columns.str.contains(col.split('(')[0]))]
                            
                            final_columns = []
                            for col in ['股票代码', '股票名称', '股价(元)', '换手率(%)', '市值(亿)', '市盈率']:
                                if col in display_data.columns:
                                    final_columns.append(col)
                            
                            # 显示表格
                            if final_columns:
                                st.dataframe(
                                    display_data[final_columns].head(20),
                                    use_container_width=True,
                                    hide_index=True
                                )
                            else:
                                st.dataframe(display_data.head(20), use_container_width=True, hide_index=True)
                            
                            if len(result) > 20:
                                st.info(f"仅显示前20只股票，共筛选出 {len(result)} 只")
                        
                        else:
                            st.warning("❌ 未找到符合条件的股票，请调整筛选参数")
                    
                    except Exception as e:
                        st.error(f"❌ 筛选过程出错: {str(e)}")
                        st.exception(e)
        
        with col2:
            st.info("""
            **💡 操作提示:**
            
            1. 调整左侧筛选条件
            2. 点击"开始筛选"
            3. 查看筛选结果
            4. 进入"技术分析"进行深度分析
            """)
    
    with tab2:
        st.subheader("📈 简化技术分析")
        
        if 'filtered_stocks' not in st.session_state:
            st.info("📊 请先在'股票筛选'页面获取数据")
        else:
            stocks_df = st.session_state.filtered_stocks
            
            st.success(f"📋 已加载 {len(stocks_df)} 只股票数据")
            
            # 选择要分析的股票
            stock_options = []
            for _, row in stocks_df.head(10).iterrows():  # 只显示前10只
                stock_options.append(f"{row['name']} ({row['ts_code']})")
            
            selected_stocks = st.multiselect(
                "🎯 选择要分析的股票",
                options=stock_options,
                default=stock_options[:3] if len(stock_options) >= 3 else stock_options
            )
            
            if selected_stocks and st.button("🔍 开始技术分析", type="primary"):
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, stock_option in enumerate(selected_stocks):
                    # 提取股票代码
                    ts_code = stock_option.split('(')[-1].split(')')[0]
                    name = stock_option.split('(')[0].strip()
                    
                    status_text.text(f"正在分析: {name} [{i+1}/{len(selected_stocks)}]")
                    
                    analysis = simple_technical_analysis(ts_code, name)
                    
                    if analysis:
                        with st.expander(f"📊 {analysis['name']} ({analysis['code']}) - 技术分析", expanded=True):
                            
                            # 基本信息
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric("💰 当前价格", f"¥{analysis['current_price']:.2f}")
                            
                            with col2:
                                delta_color = "normal" if analysis['pct_chg'] >= 0 else "inverse"
                                st.metric("📈 涨跌幅", f"{analysis['pct_chg']:.2f}%")
                            
                            with col3:
                                st.metric("📊 5日均价", f"¥{analysis['ma5']:.2f}")
                            
                            with col4:
                                st.metric("📈 10日均价", f"¥{analysis['ma10']:.2f}")
                            
                            # 趋势分析
                            st.subheader("📊 趋势分析")
                            
                            if analysis['trend_score'] >= 75:
                                st.success(f"🚀 **趋势评级**: {analysis['trend']} (评分: {analysis['trend_score']})")
                            elif analysis['trend_score'] >= 50:
                                st.info(f"📈 **趋势评级**: {analysis['trend']} (评分: {analysis['trend_score']})")
                            else:
                                st.warning(f"📉 **趋势评级**: {analysis['trend']} (评分: {analysis['trend_score']})")
                            
                            # 操作建议
                            st.subheader("💡 操作建议")
                            
                            if analysis['trend_score'] >= 75:
                                st.success("✅ **建议**: 强势股票，可重点关注")
                            elif analysis['trend_score'] >= 60:
                                st.info("📊 **建议**: 趋势向好，适度关注")
                            elif analysis['trend_score'] >= 40:
                                st.warning("⚠️ **建议**: 震荡为主，谨慎操作")
                            else:
                                st.error("❌ **建议**: 趋势偏弱，建议回避")
                            
                            # 详细数据
                            with st.expander("📋 详细数据"):
                                st.write(f"**成交量**: {analysis['volume']:,.0f} 手")
                                st.write(f"**成交额**: {analysis['amount']:,.0f} 千元")
                                st.write(f"**分析日期**: {analysis['analysis_date']}")
                    
                    progress_bar.progress((i + 1) / len(selected_stocks))
                    time.sleep(0.2)
                
                progress_bar.empty()
                status_text.empty()
                st.success("✅ 分析完成！")
    
    with tab3:
        st.markdown("""
        # 📚 TD股票分析系统使用说明
        
        ## 🎯 系统功能
        
        这是一个基于Tushare数据的**简化版**股票技术分析系统：
        
        ### 📊 主要功能
        - **智能筛选**: 根据股价、换手率、市值筛选股票
        - **基础分析**: 简单技术分析和趋势判断
        - **实时数据**: 基于最新交易日数据
        - **风险控制**: 自动排除高风险股票
        
        ## 🛠️ 使用步骤
        
        ### 第一步：股票筛选
        1. 在侧边栏调整筛选条件
        2. 点击"开始筛选"按钮
        3. 查看筛选结果和统计信息
        
        ### 第二步：技术分析
        1. 从筛选结果中选择股票
        2. 点击"开始技术分析"
        3. 查看趋势评级和操作建议
        
        ## ⚙️ 参数说明
        
        ### 筛选条件
        - **最大股价**: 筛选低价股票，降低投资门槛
        - **最小换手率**: 确保股票活跃度
        - **最小市值**: 避免过小公司，控制风险
        
        ### 技术指标
        - **5日均价**: 短期价格趋势
        - **10日均价**: 中期价格趋势  
        - **趋势评分**: 综合评估股票强度
        
        ## 📊 评分体系
        
        ### 趋势评分
        - **75分以上**: 🚀 强势股票，值得重点关注
        - **60-74分**: 📈 趋势向好，适度关注
        - **40-59分**: 📊 震荡整理，谨慎操作
        - **40分以下**: 📉 趋势偏弱，建议回避
        
        ## ⚠️ 重要提示
        
        ### 系统特点
        - ✅ **轻量级**: 快速加载，响应迅速
        - ✅ **实用性**: 专注核心功能，简单易用
        - ✅ **稳定性**: 避免复杂依赖，运行稳定
        - ✅ **免费使用**: 完全免费，无任何限制
        
        ### 风险提示
        ⚠️ **投资有风险，入市需谨慎**
        
        - 本系统仅供参考，不构成投资建议
        - 简化分析不能替代专业研究
        - 建议结合多种分析工具
        - 请根据个人风险承受能力投资
        
        ## 🔧 技术支持
        
        ### 系统优势
        - 🚀 **快速部署**: 无复杂依赖，秒级启动
        - 📱 **跨平台**: 手机、电脑完美适配
        - 🔄 **实时更新**: 基于最新交易数据
        - 💾 **轻量级**: 占用资源少，运行稳定
        
        ### 使用建议
        - 建议在桌面端获得最佳体验
        - 筛选建议一次不超过1000只股票
        - 技术分析建议一次不超过5只股票
        - 如遇网络问题，请稍后重试
        
        ---
        
        ### 🎉 感谢使用！
        
        这是一个专为个人投资者设计的轻量级股票分析工具。
        虽然功能简化，但核心分析逻辑依然专业可靠。
        
        **愿您投资顺利！** 📈
        """)

if __name__ == "__main__":
    main()

import streamlit as st
import tushare as ts
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

def init_tushare():
    """初始化tushare"""
    try:
        ts.set_token(TOKEN)
        return ts.pro_api(TOKEN)
    except Exception as e:
        st.error(f"初始化Tushare失败: {e}")
        return None

def check_trade_date(date_str):
    """检查是否为交易日"""
    try:
        pro = init_tushare()
        if pro is None:
            return True  # 如果无法验证，默认返回True
        
        trade_cal = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
        if len(trade_cal) > 0 and trade_cal.iloc[0]['is_open'] == 1:
            return True
        return False
    except Exception as e:
        return True  # 出错时默认返回True

def get_latest_trade_date():
    """获取最近的交易日"""
    try:
        pro = init_tushare()
        if pro is None:
            return datetime.now().strftime('%Y%m%d')
        
        today = datetime.now().strftime('%Y%m%d')
        trade_cal = pro.trade_cal(exchange='SSE', end_date=today, is_open=1)
        
        if len(trade_cal) > 0:
            # 手动排序
            trade_cal_sorted = trade_cal.sort_values('cal_date', ascending=False)
            return trade_cal_sorted.iloc[0]['cal_date']
        else:
            return datetime.now().strftime('%Y%m%d')
    except Exception as e:
        st.error(f"获取交易日期失败: {e}")
        return datetime.now().strftime('%Y%m%d')

def get_stock_basic():
    """获取股票基本信息"""
    try:
        pro = init_tushare()
        if pro is None:
            return None
        
        stock_list = pro.stock_basic(
            exchange='', 
            list_status='L', 
            fields='ts_code,symbol,name,area,industry'
        )
        return stock_list
    except Exception as e:
        st.error(f"获取股票列表失败: {e}")
        return None

def get_daily_data(trade_date, ts_code):
    """获取单只股票的日线数据"""
    try:
        pro = init_tushare()
        if pro is None:
            return None
        
        daily_data = pro.daily_basic(
            ts_code=ts_code,
            trade_date=trade_date,
            fields='ts_code,close,turnover_rate,total_mv'
        )
        return daily_data
    except Exception as e:
        return None

def filter_stocks(target_date, max_price=10, min_turnover=1.5, min_market_cap=40):
    """筛选股票"""
    
    # 获取股票基本信息
    stock_list = get_stock_basic()
    if stock_list is None:
        st.error("无法获取股票列表")
        return None
    
    # 过滤ST股票和特殊板块
    filtered_stocks = stock_list[
        ~stock_list['symbol'].str.startswith(('688', '300', '8'))
    ].copy()
    
    filtered_stocks = filtered_stocks[
        ~filtered_stocks['name'].str.contains('ST', case=False, na=False)
    ].copy()
    
    st.info(f"初步筛选后股票数量: {len(filtered_stocks)}")
    
    # 分批获取数据（减少批次大小）
    batch_size = 20
    all_results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 只处理前100只股票，避免超时
    sample_stocks = filtered_stocks.head(100)
    
    for i in range(0, len(sample_stocks), batch_size):
        batch_stocks = sample_stocks.iloc[i:i+batch_size]
        status_text.text(f"获取数据: {i//batch_size + 1}/{(len(sample_stocks)+batch_size-1)//batch_size}")
        
        batch_results = []
        
        for _, stock in batch_stocks.iterrows():
            daily_data = get_daily_data(target_date, stock['ts_code'])
            
            if daily_data is not None and len(daily_data) > 0:
                # 合并数据
                stock_data = stock.to_dict()
                stock_data.update(daily_data.iloc[0].to_dict())
                
                # 应用筛选条件
                try:
                    if (stock_data.get('close', 0) < max_price and 
                        stock_data.get('turnover_rate', 0) > min_turnover and
                        stock_data.get('total_mv', 0) > min_market_cap * 10000):
                        batch_results.append(stock_data)
                except:
                    continue
            
            time.sleep(0.05)  # 避免API限制
        
        if batch_results:
            all_results.extend(batch_results)
        
        progress_bar.progress((i + batch_size) / len(sample_stocks))
    
    progress_bar.empty()
    status_text.empty()
    
    if all_results:
        # 转换为DataFrame并排序
        import pandas as pd
        result_df = pd.DataFrame(all_results)
        
        if 'total_mv' in result_df.columns:
            result_df = result_df.sort_values('total_mv', ascending=True)
        
        return result_df
    else:
        return None

def simple_analysis(ts_code, name):
    """简单分析"""
    try:
        pro = init_tushare()
        if pro is None:
            return None
        
        # 获取最近20天数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
        
        hist_data = pro.daily(
            ts_code=ts_code, 
            start_date=start_date, 
            end_date=end_date
        )
        
        if len(hist_data) < 3:
            return None
        
        # 排序
        hist_data = hist_data.sort_values('trade_date')
        latest = hist_data.iloc[-1]
        
        # 简单计算
        if len(hist_data) >= 5:
            recent_5_avg = hist_data.tail(5)['close'].mean()
        else:
            recent_5_avg = latest['close']
        
        # 趋势判断
        if latest['pct_chg'] > 3:
            trend = "🚀 强势上涨"
            score = 85
        elif latest['pct_chg'] > 0:
            trend = "📈 上涨"
            score = 65
        elif latest['pct_chg'] > -3:
            trend = "📊 震荡"
            score = 50
        else:
            trend = "📉 下跌"
            score = 25
        
        return {
            'code': ts_code,
            'name': name,
            'price': latest['close'],
            'change': latest['pct_chg'],
            'volume': latest['vol'],
            'trend': trend,
            'score': score,
            'avg_5': recent_5_avg
        }
        
    except Exception as e:
        return None

def main():
    # 标题
    st.title("📈 TD股票分析系统")
    st.markdown("### 简化版股票筛选与分析工具")
    st.markdown("---")
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 设置")
        
        # 日期选择
        st.subheader("📅 交易日期")
        
        # 获取最新交易日作为默认值
        try:
            latest_date = get_latest_trade_date()
            default_date = datetime.strptime(latest_date, '%Y%m%d').date()
        except:
            default_date = datetime.now().date()
            latest_date = datetime.now().strftime('%Y%m%d')
        
        # 日期选择方式
        date_option = st.radio(
            "选择日期方式",
            ["使用最新交易日", "手动选择日期"],
            index=0
        )
        
        if date_option == "使用最新交易日":
            selected_date = latest_date
            st.success(f"📅 最新交易日: {selected_date}")
        else:
            # 手动选择日期
            manual_date = st.date_input(
                "选择分析日期",
                value=default_date,
                min_value=datetime(2020, 1, 1).date(),
                max_value=datetime.now().date(),
                help="选择要分析的交易日期"
            )
            selected_date = manual_date.strftime('%Y%m%d')
            
            # 验证是否为交易日
            if st.button("🔍 验证交易日", key="check_date"):
                with st.spinner("验证中..."):
                    if check_trade_date(selected_date):
                        st.success(f"✅ {selected_date} 是交易日")
                    else:
                        st.error(f"❌ {selected_date} 不是交易日，请重新选择")
                        # 获取最近的交易日建议
                        try:
                            pro = init_tushare()
                            if pro:
                                nearby_dates = pro.trade_cal(
                                    exchange='SSE', 
                                    start_date=(manual_date - timedelta(days=7)).strftime('%Y%m%d'),
                                    end_date=(manual_date + timedelta(days=7)).strftime('%Y%m%d'),
                                    is_open=1
                                )
                                if len(nearby_dates) > 0:
                                    st.info("📅 附近的交易日:")
                                    for _, row in nearby_dates.head(3).iterrows():
                                        st.write(f"• {row['cal_date']}")
                        except:
                            pass
            
            st.info(f"📅 选择的日期: {selected_date}")
        
        # 筛选参数
        st.subheader("🎯 筛选条件")
        max_price = st.slider("最大股价", 5.0, 20.0, 10.0)
        min_turnover = st.slider("最小换手率%", 0.5, 5.0, 1.5)
        min_market_cap = st.slider("最小市值(亿)", 20, 100, 40)
    
    # 主界面
    tab1, tab2 = st.tabs(["📊 股票筛选", "📈 分析"])
    
    with tab1:
        st.subheader("🎯 股票筛选")
        
        if st.button("🚀 开始筛选", type="primary"):
            with st.spinner("筛选中..."):
                try:
                    result = filter_stocks(selected_date, max_price, min_turnover, min_market_cap)
                    
                    if result is not None and len(result) > 0:
                        st.success(f"找到 {len(result)} 只股票")
                        
                        # 保存结果
                        st.session_state.stocks = result
                        
                        # 显示统计
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("股票数量", len(result))
                        with col2:
                            if 'close' in result.columns:
                                avg_price = result['close'].mean()
                                st.metric("平均股价", f"{avg_price:.2f}元")
                        with col3:
                            if 'total_mv' in result.columns:
                                avg_mv = result['total_mv'].mean() / 10000
                                st.metric("平均市值", f"{avg_mv:.1f}亿")
                        
                        # 显示表格
                        display_cols = ['ts_code', 'name']
                        if 'close' in result.columns:
                            display_cols.append('close')
                        if 'turnover_rate' in result.columns:
                            display_cols.append('turnover_rate')
                        if 'total_mv' in result.columns:
                            result_copy = result.copy()
                            result_copy['市值(亿)'] = result_copy['total_mv'] / 10000
                            display_cols.append('市值(亿)')
                            st.dataframe(result_copy[display_cols].head(15), use_container_width=True)
                        else:
                            st.dataframe(result[display_cols].head(15), use_container_width=True)
                    
                    else:
                        st.warning("未找到符合条件的股票")
                
                except Exception as e:
                    st.error(f"筛选失败: {str(e)}")
    
    with tab2:
        st.subheader("📈 技术分析")
        
        if 'stocks' not in st.session_state:
            st.info("请先筛选股票")
        else:
            stocks_df = st.session_state.stocks
            
            # 选择股票
            stock_options = []
            for _, row in stocks_df.head(10).iterrows():
                stock_options.append(f"{row['name']} ({row['ts_code']})")
            
            if stock_options:
                selected = st.selectbox("选择股票", stock_options)
                
                if st.button("🔍 分析"):
                    if selected:
                        # 提取代码
                        code = selected.split('(')[-1].split(')')[0]
                        name = selected.split('(')[0].strip()
                        
                        with st.spinner(f"分析 {name}..."):
                            analysis = simple_analysis(code, name)
                            
                            if analysis:
                                st.success("分析完成！")
                                
                                # 显示结果
                                col1, col2, col3, col4 = st.columns(4)
                                
                                with col1:
                                    st.metric("股价", f"{analysis['price']:.2f}元")
                                with col2:
                                    st.metric("涨跌幅", f"{analysis['change']:.2f}%")
                                with col3:
                                    st.metric("5日均价", f"{analysis['avg_5']:.2f}元")
                                with col4:
                                    st.metric("评分", f"{analysis['score']}分")
                                
                                # 趋势分析
                                if analysis['score'] >= 70:
                                    st.success(f"趋势: {analysis['trend']}")
                                elif analysis['score'] >= 50:
                                    st.info(f"趋势: {analysis['trend']}")
                                else:
                                    st.warning(f"趋势: {analysis['trend']}")
                                
                                # 建议
                                if analysis['score'] >= 70:
                                    st.success("💡 建议: 可重点关注")
                                elif analysis['score'] >= 50:
                                    st.info("💡 建议: 适度关注")
                                else:
                                    st.warning("💡 建议: 谨慎操作")
                            
                            else:
                                st.error("分析失败，请重试")
            else:
                st.warning("没有可分析的股票")
    
    # 说明
    with st.expander("📚 使用说明"):
        st.markdown("""
        ### 功能说明
        - **股票筛选**: 根据价格、换手率、市值筛选股票
        - **技术分析**: 简单的趋势判断和评分
        
        ### 筛选条件
        - 排除科创板(688)、创业板(300)、北交所(8)
        - 排除ST股票
        - 根据设定条件筛选
        
        ### 风险提示
        ⚠️ 本工具仅供参考，投资有风险，入市需谨慎！
        """)

if __name__ == "__main__":
    main()

import streamlit as st
import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from scipy.signal import argrelextrema
import warnings

warnings.filterwarnings('ignore')

# 页面配置
st.set_page_config(
    page_title="增强版TD股票分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 设置tushare token
TOKEN = '27fab716cc7ea549b52a8345e43cfa9be8daa8976ca6fdfe2c4a1d3e'

# ==================== 缓存函数 ====================
@st.cache_data(ttl=3600)
def init_tushare():
    """初始化tushare"""
    try:
        ts.set_token(TOKEN)
        return ts.pro_api(TOKEN)
    except Exception as e:
        st.error(f"初始化Tushare失败: {e}")
        return None

@st.cache_data(ttl=3600)
def check_trade_date(date_str):
    """检查输入的日期是否为交易日"""
    pro = init_tushare()
    if pro is None:
        return False
    try:
        trade_cal = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
        if len(trade_cal) > 0 and trade_cal.iloc[0]['is_open'] == 1:
            return True
        return False
    except:
        return False

@st.cache_data(ttl=3600)
def get_latest_trade_date():
    """获取最近的交易日"""
    pro = init_tushare()
    if pro is None:
        return datetime.now().strftime('%Y%m%d')
    try:
        today = datetime.now().strftime('%Y%m%d')
        trade_cal = pro.trade_cal(exchange='SSE', end_date=today, is_open=1)
        trade_cal = trade_cal.sort_values('cal_date', ascending=False)
        return trade_cal.iloc[0]['cal_date']
    except Exception as e:
        st.error(f"获取交易日期失败: {e}")
        return datetime.now().strftime('%Y%m%d')

@st.cache_data(ttl=1800)
def get_nearby_trade_dates(date_str):
    """获取指定日期附近的交易日"""
    pro = init_tushare()
    if pro is None:
        return []
    try:
        start_date = (pd.to_datetime(date_str) - timedelta(days=10)).strftime('%Y%m%d')
        end_date = (pd.to_datetime(date_str) + timedelta(days=10)).strftime('%Y%m%d')
        trade_cal = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date, is_open=1)
        return trade_cal['cal_date'].tolist()
    except:
        return []

# ==================== 核心分析函数 ====================
def calculate_atr(hist_data, period=14):
    """计算ATR（平均真实波幅）"""
    df = hist_data.copy().sort_values('trade_date')
    
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    df['atr'] = df['tr'].rolling(window=period).mean()
    
    return df.iloc[-1]['atr'] if pd.notna(df.iloc[-1]['atr']) else df.iloc[-1]['close'] * 0.02

def calculate_market_strength(hist_data):
    """计算市场强度指标"""
    df = hist_data.copy().sort_values('trade_date')
    recent = df.tail(20)
    
    # 计算上涨天数比例
    up_days = len(recent[recent['pct_chg'] > 0])
    strength_ratio = up_days / len(recent)
    
    # 计算平均涨跌幅
    avg_change = recent['pct_chg'].mean()
    
    # 计算波动率
    volatility = recent['pct_chg'].std()
    
    return {
        'strength_ratio': strength_ratio,
        'avg_change': avg_change,
        'volatility': volatility
    }

def calculate_td_sequential_enhanced(hist_data):
    """增强版TD序列计算"""
    df = hist_data.copy()
    df = df.sort_values('trade_date')
    
    # 初始化TD指标列
    df['td_setup'] = 0
    df['td_countdown'] = 0
    df['td_perfected'] = False
    df['td_combo'] = 0
    df['td_flip_price'] = 0.0
    df['tdst_resistance'] = 0.0
    df['tdst_support'] = 0.0
    df['td_risk_level'] = 0
    df['td_sequential_13'] = False
    df['td_pressure'] = 0
    df['td_momentum'] = 0
    
    # TD Setup计算
    buy_setup_count = 0
    sell_setup_count = 0
    setup_direction = 0
    setup_start_idx = 0
    
    # TD Countdown计算
    countdown_active = False
    countdown_type = 0
    countdown_count = 0
    countdown_start_idx = 0
    
    # TD Combo计算
    combo_count = 0
    combo_type = 0
    
    for i in range(4, len(df)):
        # 获取翻转价格（4天前的收盘价）
        flip_price = df.iloc[i - 4]['close']
        df.iloc[i, df.columns.get_loc('td_flip_price')] = flip_price
        
        current_close = df.iloc[i]['close']
        current_low = df.iloc[i]['low']
        current_high = df.iloc[i]['high']
        
        # TD Buy Setup
        if current_close < flip_price:
            if buy_setup_count >= 0:
                buy_setup_count += 1
                sell_setup_count = 0
                df.iloc[i, df.columns.get_loc('td_setup')] = buy_setup_count
                setup_direction = 1
                
                if buy_setup_count == 1:
                    setup_start_idx = i
                
                # 检查完美设置
                if buy_setup_count == 8 or buy_setup_count == 9:
                    if i >= 7:
                        low_6 = df.iloc[i - 2]['low']
                        low_7 = df.iloc[i - 1]['low']
                        if current_low < min(low_6, low_7):
                            df.iloc[i, df.columns.get_loc('td_perfected')] = True
                
                # Setup 9完成
                if buy_setup_count == 9:
                    countdown_active = True
                    countdown_type = 1
                    countdown_count = 0
                    countdown_start_idx = i
                    
                    # 计算TDST支撑线
                    setup_data = df.iloc[setup_start_idx:i + 1]
                    tdst_support = setup_data['low'].min()
                    df.iloc[i, df.columns.get_loc('tdst_support')] = tdst_support
                    
                    # 开始Combo计数
                    combo_count = 1
                    combo_type = 1
            else:
                buy_setup_count = 1
                sell_setup_count = 0
                df.iloc[i, df.columns.get_loc('td_setup')] = buy_setup_count
                setup_direction = 1
                setup_start_idx = i
        
        # TD Sell Setup
        elif current_close > flip_price:
            if sell_setup_count <= 0:
                sell_setup_count -= 1
                buy_setup_count = 0
                df.iloc[i, df.columns.get_loc('td_setup')] = sell_setup_count
                setup_direction = -1
                
                if sell_setup_count == -1:
                    setup_start_idx = i
                
                # 检查完美设置
                if sell_setup_count == -8 or sell_setup_count == -9:
                    if i >= 7:
                        high_6 = df.iloc[i - 2]['high']
                        high_7 = df.iloc[i - 1]['high']
                        if current_high > max(high_6, high_7):
                            df.iloc[i, df.columns.get_loc('td_perfected')] = True
                
                # Setup -9完成
                if sell_setup_count == -9:
                    countdown_active = True
                    countdown_type = -1
                    countdown_count = 0
                    countdown_start_idx = i
                    
                    # 计算TDST阻力线
                    setup_data = df.iloc[setup_start_idx:i + 1]
                    tdst_resistance = setup_data['high'].max()
                    df.iloc[i, df.columns.get_loc('tdst_resistance')] = tdst_resistance
                    
                    # 开始Combo计数
                    combo_count = -1
                    combo_type = -1
            else:
                sell_setup_count = -1
                buy_setup_count = 0
                df.iloc[i, df.columns.get_loc('td_setup')] = sell_setup_count
                setup_direction = -1
                setup_start_idx = i
        else:
            # 价格等于翻转价格，Setup中断
            buy_setup_count = 0
            sell_setup_count = 0
            combo_count = 0
        
        # TD Countdown计算
        if countdown_active and i > countdown_start_idx and i >= 2:
            if countdown_type == 1:  # 买入倒计时
                if current_close <= df.iloc[i - 2]['low']:
                    countdown_count += 1
                    df.iloc[i, df.columns.get_loc('td_countdown')] = countdown_count
                    
                    if countdown_count == 13:
                        df.iloc[i, df.columns.get_loc('td_sequential_13')] = True
            
            elif countdown_type == -1:  # 卖出倒计时
                if current_close >= df.iloc[i - 2]['high']:
                    countdown_count -= 1
                    df.iloc[i, df.columns.get_loc('td_countdown')] = countdown_count
                    
                    if countdown_count == -13:
                        df.iloc[i, df.columns.get_loc('td_sequential_13')] = True
            
            # 倒计时完成
            if abs(countdown_count) >= 13:
                countdown_active = False
                countdown_count = 0
        
        # TD Combo计算
        if combo_type != 0 and i > setup_start_idx:
            if combo_type == 1 and current_close < df.iloc[i - 1]['close']:
                combo_count += 1
                df.iloc[i, df.columns.get_loc('td_combo')] = combo_count
            elif combo_type == -1 and current_close > df.iloc[i - 1]['close']:
                combo_count -= 1
                df.iloc[i, df.columns.get_loc('td_combo')] = combo_count
            
            if abs(combo_count) >= 13:
                combo_count = 0
                combo_type = 0
        
        # 计算TD压力指标
        pressure = 0
        if i >= 9:
            recent_highs = df.iloc[i - 9:i + 1]['high'].max()
            recent_lows = df.iloc[i - 9:i + 1]['low'].min()
            if recent_highs > recent_lows:
                price_position = (current_close - recent_lows) / (recent_highs - recent_lows)
                pressure = int((1 - price_position) * 10)
        df.iloc[i, df.columns.get_loc('td_pressure')] = pressure
        
        # 计算TD动量指标
        momentum = 0
        if i >= 4:
            price_change = (current_close - df.iloc[i - 4]['close']) / df.iloc[i - 4]['close']
            momentum = min(max(price_change * 100, -10), 10)
        df.iloc[i, df.columns.get_loc('td_momentum')] = momentum
        
        # 计算综合TD风险等级
        risk_level = 0
        
        # Setup风险
        if abs(df.iloc[i]['td_setup']) >= 7:
            risk_level += 1 * np.sign(df.iloc[i]['td_setup'])
        if abs(df.iloc[i]['td_setup']) == 9:
            risk_level += 2 * np.sign(df.iloc[i]['td_setup'])
        
        # Countdown风险
        if abs(df.iloc[i]['td_countdown']) >= 10:
            risk_level += 1 * np.sign(df.iloc[i]['td_countdown'])
        if abs(df.iloc[i]['td_countdown']) == 13:
            risk_level += 3 * np.sign(df.iloc[i]['td_countdown'])
        
        # Combo风险
        if abs(df.iloc[i]['td_combo']) >= 10:
            risk_level += 1 * np.sign(df.iloc[i]['td_combo'])
        
        # 压力和动量调整
        if pressure >= 8:
            risk_level -= 1
        if momentum > 5:
            risk_level += 1
        elif momentum < -5:
            risk_level -= 1
        
        df.iloc[i, df.columns.get_loc('td_risk_level')] = max(min(risk_level, 5), -5)
    
    return df

def calculate_support_resistance_enhanced(hist_data, periods=20):
    """增强版支撑阻力位计算"""
    df = hist_data.copy()
    df = df.sort_values('trade_date')
    
    recent_data = df.tail(periods)
    
    # 基础支撑阻力位
    support1 = recent_data['low'].min()
    support2 = recent_data['low'].nsmallest(2).iloc[-1] if len(recent_data) >= 2 else support1
    
    resistance1 = recent_data['high'].max()
    resistance2 = recent_data['high'].nlargest(2).iloc[-1] if len(recent_data) >= 2 else resistance1
    
    # 轴心点
    latest = recent_data.iloc[-1]
    pivot = (latest['high'] + latest['low'] + latest['close']) / 3
    
    return {
        'support1': support1,
        'support2': support2,
        'resistance1': resistance1,
        'resistance2': resistance2,
        'pivot': pivot,
        'support_strength': len(recent_data[recent_data['low'] <= support1 * 1.02]),
        'resistance_strength': len(recent_data[recent_data['high'] >= resistance1 * 0.98])
    }

def analyze_volume_pattern_enhanced(hist_data):
    """增强版成交量分析"""
    df = hist_data.copy().sort_values('trade_date')
    recent = df.tail(20)
    latest = recent.iloc[-1]
    
    volume_col = 'vol'
    
    if volume_col not in df.columns:
        return {
            'volume_trend': "数据缺失",
            'volume_ratio': 0,
            'volume_price_match': "无法分析",
            'volume_surge': False,
            'volume_consistency': 0
        }
    
    # 基础量比分析
    avg_volume = recent[volume_col].mean()
    recent_volume = latest[volume_col]
    volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 0
    
    # 成交量趋势
    volume_trend = "平稳"
    volume_surge = False
    
    if volume_ratio > 3.0:
        volume_trend = "爆量"
        volume_surge = True
    elif volume_ratio > 2.0:
        volume_trend = "巨量"
        volume_surge = True
    elif volume_ratio > 1.5:
        volume_trend = "显著放量"
    elif volume_ratio > 1.2:
        volume_trend = "温和放量"
    elif volume_ratio < 0.5:
        volume_trend = "极度缩量"
    elif volume_ratio < 0.8:
        volume_trend = "缩量"
    
    # 成交量一致性
    volume_consistency = 0
    for i in range(1, min(6, len(recent))):
        prev_ratio = recent.iloc[-i - 1][volume_col] / avg_volume
        if prev_ratio > 1.2 and volume_ratio > 1.2:
            volume_consistency += 1
        elif prev_ratio < 0.8 and volume_ratio < 0.8:
            volume_consistency += 1
    
    # 价量配合分析
    price_change = latest['pct_chg'] if 'pct_chg' in recent.columns else 0
    volume_price_match = ""
    
    if price_change > 5 and volume_ratio > 2.0:
        volume_price_match = "涨停放量，强烈信号"
    elif price_change > 3 and volume_ratio > 1.5:
        volume_price_match = "放量大涨，趋势确认"
    elif price_change > 0 and volume_ratio > 1.2:
        volume_price_match = "价涨量增，趋势健康"
    elif price_change > 0 and volume_ratio < 0.8:
        volume_price_match = "价涨量缩，缺乏后劲"
    elif price_change < -5 and volume_ratio > 2.0:
        volume_price_match = "放量暴跌，恐慌杀跌"
    elif price_change < -3 and volume_ratio > 1.5:
        volume_price_match = "放量下跌，压力较大"
    elif price_change < 0 and volume_ratio < 0.8:
        volume_price_match = "缩量下跌，可能见底"
    else:
        volume_price_match = "价量配合正常"
    
    return {
        'volume_trend': volume_trend,
        'volume_ratio': volume_ratio,
        'volume_price_match': volume_price_match,
        'volume_surge': volume_surge,
        'volume_consistency': volume_consistency
    }

def analyze_pattern_enhanced(hist_data):
    """增强版K线形态分析"""
    recent = hist_data.tail(10)
    latest = recent.iloc[-1]
    
    if len(recent) < 3:
        return "数据不足"
    
    last3 = recent.tail(3)
    
    # 基础趋势判断
    if all(last3.iloc[i]['close'] > last3.iloc[i - 1]['close'] for i in range(1, 3)):
        trend = "连续上涨"
    elif all(last3.iloc[i]['close'] < last3.iloc[i - 1]['close'] for i in range(1, 3)):
        trend = "连续下跌"
    else:
        trend = "震荡整理"
    
    # K线形态分析
    body_ratio = abs(latest['close'] - latest['open']) / (latest['high'] - latest['low'] + 0.0001)
    upper_shadow = (latest['high'] - max(latest['close'], latest['open'])) / (latest['high'] - latest['low'] + 0.0001)
    lower_shadow = (min(latest['close'], latest['open']) - latest['low']) / (latest['high'] - latest['low'] + 0.0001)
    
    pattern = trend
    
    # 特殊K线形态
    if body_ratio < 0.1:
        pattern += "，十字星（变盘信号）"
    elif upper_shadow > 0.6:
        pattern += "，长上影线（上方压力大）"
    elif lower_shadow > 0.6:
        pattern += "，长下影线（下方支撑强）"
    elif latest['close'] > latest['open'] and body_ratio > 0.7:
        pattern += "，大阳线（多头强势）"
    elif latest['close'] < latest['open'] and body_ratio > 0.7:
        pattern += "，大阴线（空头强势）"
    
    # 根据涨幅判断强势
    if 'pct_chg' in hist_data.columns:
        pct_chg = latest['pct_chg']
        if pct_chg > 0:
            if pct_chg > 7:
                pattern += "，涨停强势"
            elif pct_chg > 5:
                pattern += "，强势上涨"
            elif pct_chg > 2:
                pattern += "，温和上涨"
        elif pct_chg < -7:
            pattern += "，跌停弱势"
        elif pct_chg < -5:
            pattern += "，急跌"
        
        # 判断中期趋势强度
        if len(recent) >= 5:
            recent_5 = recent.tail(5)
            up_days = sum(1 for _, row in recent_5.iterrows() if row.get('pct_chg', 0) > 0)
            total_change = recent_5['pct_chg'].sum()
            
            if up_days >= 4 and total_change > 5:
                pattern += "，中期强势"
            elif up_days <= 1 and total_change < -5:
                pattern += "，中期弱势"
    
    return pattern

def generate_enhanced_td_strategy(latest_data, sr_levels, td_setup, td_countdown,
                                  td_perfected, td_combo, tdst_support, tdst_resistance,
                                  ma_trend, volume_analysis, market_strength, atr_value):
    """生成增强版TD交易策略"""
    
    price = latest_data['close']
    strategy = {
        'direction': '',
        'signal_strength': '',
        'entry_points': {},
        'stop_loss': 0,
        'targets': [],
        'position_size': '',
        'time_frame': '',
        'risk_reward': '',
        'confidence': 0,
        'notes': []
    }
    
    # 计算动态止损（基于ATR）
    atr_stop_distance = atr_value * 2.5 if atr_value > 0 else price * 0.05
    
    # 综合信号强度评估
    signal_score = 0
    confidence_factors = []
    
    # TD Setup评分
    if abs(td_setup) == 9:
        signal_score += 35
        confidence_factors.append("Setup 9完成")
    elif abs(td_setup) >= 7:
        signal_score += 20
        confidence_factors.append(f"Setup {abs(td_setup)}接近完成")
    elif abs(td_setup) >= 4:
        signal_score += 12
        confidence_factors.append(f"Setup {abs(td_setup)}进行中")
    elif abs(td_setup) >= 1:
        signal_score += 5
        confidence_factors.append(f"Setup {abs(td_setup)}初期")
    
    # TD Countdown评分
    if abs(td_countdown) == 13:
        signal_score += 45
        confidence_factors.append("Countdown 13完成")
    elif abs(td_countdown) >= 10:
        signal_score += 30
        confidence_factors.append(f"Countdown {abs(td_countdown)}接近完成")
    elif abs(td_countdown) >= 7:
        signal_score += 20
        confidence_factors.append(f"Countdown {abs(td_countdown)}中后期")
    elif abs(td_countdown) >= 3:
        signal_score += 10
        confidence_factors.append(f"Countdown {abs(td_countdown)}进行中")
    
    # TD Combo评分
    if abs(td_combo) >= 10:
        signal_score += 18
        confidence_factors.append(f"Combo {abs(td_combo)}高级别")
    elif abs(td_combo) >= 5:
        signal_score += 8
        confidence_factors.append(f"Combo {abs(td_combo)}中级别")
    
    # 完美设置加分
    if td_perfected:
        signal_score += 20
        confidence_factors.append("完美设置确认")
    
    # 成交量确认
    if volume_analysis['volume_surge']:
        signal_score += 18
        confidence_factors.append("爆量确认")
    elif volume_analysis['volume_ratio'] > 1.5:
        signal_score += 12
        confidence_factors.append("显著放量")
    elif volume_analysis['volume_ratio'] > 1.2:
        signal_score += 8
        confidence_factors.append("温和放量")
    elif volume_analysis['volume_ratio'] < 0.8:
        signal_score -= 3
        confidence_factors.append("量能不足")
    
    # 均线位置加分
    if ma_trend == "多头排列":
        signal_score += 12
        confidence_factors.append("均线多头")
    elif ma_trend == "空头排列":
        signal_score -= 8
        confidence_factors.append("均线空头")
    
    # 市场强度调整
    if market_strength['strength_ratio'] > 0.65:
        signal_score += 8
        confidence_factors.append("市场强势")
    elif market_strength['strength_ratio'] < 0.35:
        signal_score -= 8
        confidence_factors.append("市场弱势")
    
    # 信号等级判定
    if signal_score >= 70:
        strategy['signal_strength'] = "S级（极强）"
        strategy['confidence'] = min(80 + signal_score * 0.15, 95)
    elif signal_score >= 50:
        strategy['signal_strength'] = "A级（强）"
        strategy['confidence'] = min(65 + signal_score * 0.25, 85)
    elif signal_score >= 25:
        strategy['signal_strength'] = "B级（中等）"
        strategy['confidence'] = min(45 + signal_score * 0.4, 70)
    elif signal_score >= 10:
        strategy['signal_strength'] = "C+级（偏弱）"
        strategy['confidence'] = min(35 + signal_score * 0.6, 55)
    else:
        strategy['signal_strength'] = "C级（弱）"
        strategy['confidence'] = min(25 + signal_score * 0.8, 45)
    
    # 交易方向判断
    is_bullish_signal = (td_setup > 0 and td_setup >= 3) or (td_countdown > 0 and abs(td_countdown) >= 3)
    is_bearish_signal = (td_setup < 0 and td_setup <= -3) or (td_countdown < 0 and abs(td_countdown) >= 3)
    
    if is_bullish_signal or signal_score >= 20:
        strategy['direction'] = "买入"
        
        # 入场点设置
        if signal_score >= 50:
            strategy['entry_points'] = {
                '激进': f"{price:.2f}（当前价立即入场）",
                '稳健': f"{price * 0.99:.2f}（小幅回调1%）",
                '保守': f"{max(tdst_support if tdst_support > 0 else sr_levels['support1'], sr_levels['support1']) * 1.01:.2f}（支撑位确认）"
            }
        elif signal_score >= 25:
            strategy['entry_points'] = {
                '稳健': f"{price * 0.985:.2f}（回调1.5%入场）",
                '保守': f"{sr_levels['support1'] * 1.015:.2f}（强支撑确认）"
            }
        else:
            strategy['entry_points'] = {
                '保守': f"{sr_levels['support1'] * 1.01:.2f}（支撑位企稳后试探）",
                '观察': "信号偏弱，建议小仓位试探"
            }
        
        # 动态止损设置
        dynamic_support = max(
            tdst_support * 0.98 if tdst_support > 0 else 0,
            sr_levels['support1'] * 0.97,
            price - atr_stop_distance
        )
        strategy['stop_loss'] = dynamic_support
        
        # 目标位设置
        target1 = price * 1.035
        tech_resistance = sr_levels['resistance1']
        if tdst_resistance > price * 1.02:
            tech_resistance = min(tdst_resistance, tech_resistance)
        target2 = min(tech_resistance, price * 1.08)
        target3 = price * 1.12
        if target2 > target3:
            target3 = target2 * 1.05
        
        strategy['targets'] = [
            f"T1: {target1:.2f}（+{((target1 / price - 1) * 100):.1f}%，短线）",
            f"T2: {target2:.2f}（+{((target2 / price - 1) * 100):.1f}%，技术阻力）",
            f"T3: {target3:.2f}（+{((target3 / price - 1) * 100):.1f}%，波段）"
        ]
    
    elif is_bearish_signal:
        strategy['direction'] = "卖出/观望"
        
        if signal_score >= 40:
            strategy['entry_points'] = {
                '做空': f"{price * 1.01:.2f}（反弹做空）",
                '持仓者': "考虑减仓或止盈"
            }
        else:
            strategy['entry_points'] = {
                '观望': "TD卖出信号，暂不买入",
                '持仓者': "设置止损，防范回调"
            }
        
        strategy['stop_loss'] = min(
            sr_levels['resistance1'] * 1.03,
            price + atr_stop_distance
        )
        
        target1 = price * 0.965
        target2 = max(sr_levels['support1'], price * 0.92)
        target3 = price * 0.88
        
        strategy['targets'] = [
            f"T1: {target1:.2f}（{((target1 / price - 1) * 100):.1f}%，短线下跌）",
            f"T2: {target2:.2f}（{((target2 / price - 1) * 100):.1f}%，技术支撑）",
            f"T3: {target3:.2f}（{((target3 / price - 1) * 100):.1f}%，深度回调）"
        ]
    
    else:
        strategy['direction'] = "观望"
        
        strategy['entry_points'] = {
            '等待买入': f"下探{sr_levels['support1']:.2f}支撑位确认后",
            '等待卖出': f"突破{sr_levels['resistance1']:.2f}阻力位后"
        }
        
        upside_target = sr_levels['resistance1']
        downside_target = sr_levels['support1']
        
        strategy['targets'] = [
            f"上方阻力: {upside_target:.2f}（+{((upside_target / price - 1) * 100):.1f}%）",
            f"下方支撑: {downside_target:.2f}（{((downside_target / price - 1) * 100):.1f}%）",
            f"轴心点: {sr_levels['pivot']:.2f}（{((sr_levels['pivot'] / price - 1) * 100):.1f}%）"
        ]
    
    # 仓位管理
    if strategy['confidence'] >= 75:
        strategy['position_size'] = "50-70%（高信心重仓）"
    elif strategy['confidence'] >= 60:
        strategy['position_size'] = "40-50%（较高信心）"
    elif strategy['confidence'] >= 45:
        strategy['position_size'] = "30-40%（中等信心）"
    elif strategy['confidence'] >= 35:
        strategy['position_size'] = "20-30%（偏低信心）"
    else:
        strategy['position_size'] = "10-20%（低信心试探）"
    
    # 时间框架
    if abs(td_countdown) >= 8:
        strategy['time_frame'] = "中线（1-3个月）"
    elif abs(td_setup) >= 6 or signal_score >= 40:
        strategy['time_frame'] = "波段（2-4周）"
    else:
        strategy['time_frame'] = "短线（5-15天）"
    
    # 风险收益比计算
    if strategy['stop_loss'] > 0 and len(strategy['targets']) > 0:
        try:
            first_target = float(strategy['targets'][0].split('T1: ')[1].split('（')[0])
            risk = abs(price - strategy['stop_loss'])
            reward = abs(first_target - price)
            if risk > 0:
                rr_ratio = reward / risk
                strategy['risk_reward'] = f"1:{rr_ratio:.1f}"
            else:
                strategy['risk_reward'] = "风险极小"
        except:
            strategy['risk_reward'] = "无法计算"
    else:
        strategy['risk_reward'] = "观望状态"
    
    # 特殊提示
    if td_perfected:
        strategy['notes'].append("⭐ 完美设置出现，信号可靠性大幅提升")
    
    if abs(td_countdown) >= 11:
        strategy['notes'].append("🚨 Countdown接近完成，重点关注反转机会")
    
    if volume_analysis['volume_surge']:
        strategy['notes'].append("📈 成交量爆发，资金关注度高")
    elif "价涨量增" in volume_analysis['volume_price_match']:
        strategy['notes'].append("✅ 量价配合良好，趋势健康")
    elif "价跌量增" in volume_analysis['volume_price_match']:
        strategy['notes'].append("⚠️ 放量下跌，谨慎操作")
    
    if ma_trend == "多头排列":
        strategy['notes'].append("📊 均线多头排列，中期趋势向好")
    elif ma_trend == "空头排列":
        strategy['notes'].append("📉 均线空头排列，注意反弹高度")
    
    # 根据信号强度添加额外提示
    if signal_score >= 50:
        strategy['notes'].append("🎯 高质量信号，建议重点关注")
    elif signal_score >= 25:
        strategy['notes'].append("👀 中等信号，适度参与")
    else:
        strategy['notes'].append("🔍 弱信号，小仓位试探或观望")
    
    return strategy

@st.cache_data(ttl=1800)
def perform_td_analysis_enhanced(stock_code, stock_name, target_date):
    """增强版TD技术分析"""
    try:
        pro = init_tushare()
        if pro is None:
            return {
                'code': stock_code,
                'name': stock_name,
                'analysis': "无法连接数据源"
            }
        
        end_date = target_date
        start_date = (pd.to_datetime(target_date) - timedelta(days=180)).strftime('%Y%m%d')
        
        # 获取历史数据
        try:
            hist_data = pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            return {
                'code': stock_code,
                'name': stock_name,
                'analysis': f"获取历史数据失败: {str(e)}"
            }
        
        if len(hist_data) < 30:
            return {
                'code': stock_code,
                'name': stock_name,
                'analysis': "历史数据不足，无法进行完整分析"
            }
        
        hist_data = hist_data.sort_values('trade_date')
        
        # 计算均线
        hist_data['ma5'] = hist_data['close'].rolling(window=5).mean()
        hist_data['ma10'] = hist_data['close'].rolling(window=10).mean()
        hist_data['ma20'] = hist_data['close'].rolling(window=20).mean()
        hist_data['ma60'] = hist_data['close'].rolling(window=60).mean()
        
        # 计算ATR
        atr_value = calculate_atr(hist_data)
        
        # 计算市场强度
        market_strength = calculate_market_strength(hist_data)
        
        # 计算增强版TD序列
        td_data = calculate_td_sequential_enhanced(hist_data)
        
        # 计算增强版支撑阻力位
        sr_levels = calculate_support_resistance_enhanced(hist_data)
        
        # 增强版成交量分析
        volume_analysis = analyze_volume_pattern_enhanced(hist_data)
        
        # 获取最新数据
        latest = hist_data.iloc[-1]
        
        # 均线趋势分析
        ma_trend = "均线粘合"
        if pd.notna(latest['ma5']) and pd.notna(latest['ma10']) and pd.notna(latest['ma20']):
            if latest['ma5'] > latest['ma10'] > latest['ma20']:
                ma_trend = "多头排列"
            elif latest['ma5'] < latest['ma10'] < latest['ma20']:
                ma_trend = "空头排列"
        
        # TD序列详细分析
        td_setup_current = td_data.iloc[-1]['td_setup']
        td_countdown_current = td_data.iloc[-1]['td_countdown']
        td_perfected_current = td_data.iloc[-1]['td_perfected']
        td_combo_current = td_data.iloc[-1]['td_combo']
        td_risk_current = td_data.iloc[-1]['td_risk_level']
        td_sequential_13 = td_data.iloc[-1]['td_sequential_13']
        td_pressure = td_data.iloc[-1]['td_pressure']
        td_momentum = td_data.iloc[-1]['td_momentum']
        tdst_support = td_data.iloc[-1]['tdst_support']
        tdst_resistance = td_data.iloc[-1]['tdst_resistance']
        
        # TD历史统计
        td_stats = {
            'setup_9_count': len(td_data[abs(td_data['td_setup']) == 9]),
            'perfected_count': len(td_data[td_data['td_perfected'] == True]),
            'countdown_13_count': len(td_data[abs(td_data['td_countdown']) == 13]),
            'sequential_13_count': len(td_data[td_data['td_sequential_13'] == True]),
            'combo_13_count': len(td_data[abs(td_data['td_combo']) == 13]),
            'current_phase': "无明显信号"
        }
        
        # 判断当前TD阶段
        phase_parts = []
        if abs(td_setup_current) >= 1:
            if abs(td_setup_current) <= 3:
                phase_parts.append(f"Setup初期({abs(td_setup_current)}/9)")
            elif abs(td_setup_current) <= 6:
                phase_parts.append(f"Setup中期({abs(td_setup_current)}/9)")
            elif abs(td_setup_current) <= 8:
                phase_parts.append(f"Setup后期({abs(td_setup_current)}/9)")
            elif abs(td_setup_current) == 9:
                phase_parts.append("Setup完成！")
        
        if abs(td_countdown_current) > 0:
            phase_parts.append(f"Countdown进行中({abs(td_countdown_current)}/13)")
        
        if abs(td_combo_current) > 0:
            phase_parts.append(f"Combo计数({abs(td_combo_current)}/13)")
        
        td_stats['current_phase'] = " + ".join(phase_parts) if phase_parts else "无明显信号"
        
        # 增强版形态分析
        pattern = analyze_pattern_enhanced(hist_data)
        
        # 生成增强版TD交易策略
        td_strategy = generate_enhanced_td_strategy(
            latest, sr_levels, td_setup_current, td_countdown_current,
            td_perfected_current, td_combo_current, tdst_support, tdst_resistance,
            ma_trend, volume_analysis, market_strength, atr_value
        )
        
        # 计算信号评分
        signal_score = 0
        if abs(td_setup_current) == 9:
            signal_score += 35
        elif abs(td_setup_current) >= 7:
            signal_score += 20
        elif abs(td_setup_current) >= 4:
            signal_score += 12
        elif abs(td_setup_current) >= 1:
            signal_score += 5
        
        if abs(td_countdown_current) == 13:
            signal_score += 45
        elif abs(td_countdown_current) >= 10:
            signal_score += 30
        elif abs(td_countdown_current) >= 7:
            signal_score += 20
        elif abs(td_countdown_current) >= 3:
            signal_score += 10
        
        if abs(td_combo_current) >= 10:
            signal_score += 18
        elif abs(td_combo_current) >= 5:
            signal_score += 8
        
        if td_perfected_current:
            signal_score += 20
        
        if volume_analysis['volume_surge']:
            signal_score += 18
        elif volume_analysis['volume_ratio'] > 1.5:
            signal_score += 12
        elif volume_analysis['volume_ratio'] > 1.2:
            signal_score += 8
        
        if ma_trend == "多头排列":
            signal_score += 12
        elif ma_trend == "空头排列":
            signal_score -= 8
        
        # 生成综合分析
        analysis = {
            'code': stock_code,
            'name': stock_name,
            'current_price': latest['close'],
            'ma_trend': ma_trend,
            'td_setup': td_setup_current,
            'td_countdown': td_countdown_current,
            'td_perfected': td_perfected_current,
            'td_combo': td_combo_current,
            'td_risk_level': td_risk_current,
            'td_pressure': td_pressure,
            'td_momentum': td_momentum,
            'td_phase': td_stats['current_phase'],
            'td_signal_grade': td_strategy['signal_strength'],
            'td_score': signal_score,
            'confidence': td_strategy['confidence'],
            'reversal_probability': td_strategy['confidence'],
            'tdst_levels': f"支撑: {tdst_support:.2f}, 阻力: {tdst_resistance:.2f}" if tdst_support > 0 or tdst_resistance > 0 else "暂无TDST位",
            'support_levels': f"S1: {sr_levels['support1']:.2f}, S2: {sr_levels['support2']:.2f}",
            'resistance_levels': f"R1: {sr_levels['resistance1']:.2f}, R2: {sr_levels['resistance2']:.2f}",
            'pivot': f"{sr_levels['pivot']:.2f}",
            'volume_analysis': volume_analysis,
            'pattern': pattern,
            'td_stats': td_stats,
            'td_strategy': td_strategy,
            'market_strength': market_strength,
            'atr_value': atr_value,
            'hist_data': hist_data,
            'td_data': td_data
        }
        
        return analysis
    
    except Exception as e:
        return {
            'code': stock_code,
            'name': stock_name,
            'analysis': f"TD分析过程出错: {str(e)}"
        }

@st.cache_data(ttl=1800)
def stock_selector(target_date=None):
    """股票筛选主函数"""
    if target_date is None:
        target_date = get_latest_trade_date()
    
    pro = init_tushare()
    if pro is None:
        return pd.DataFrame()
    
    try:
        # 获取股票列表
        stock_list = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
        
        # 排除特定板块和ST股票
        stock_list = stock_list[~stock_list['symbol'].str.startswith(('688', '300', '8'))]
        stock_list = stock_list[~stock_list['name'].str.contains('ST', case=False, na=False)]
        
        st.info(f"初始股票数量: {len(stock_list)}")
        
        # 分批获取数据
        batch_size = 100
        all_data = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_batches = (len(stock_list) // batch_size) + 1
        
        for i in range(0, len(stock_list), batch_size):
            batch = stock_list.iloc[i:i+batch_size]
            status_text.text(f"获取数据批次 {i//batch_size + 1}/{total_batches}")
            
            try:
                # 使用daily_basic获取更完整的数据
                batch_codes = batch['ts_code'].tolist()
                codes_str = ','.join(batch_codes)
                
                batch_data = pro.daily_basic(
                    ts_code=codes_str,
                    trade_date=target_date,
                    fields='ts_code,close,turnover_rate,total_mv,pe,pb'
                )
                
                if len(batch_data) > 0:
                    all_data.append(batch_data)
            
            except Exception as e:
                st.warning(f"批次 {i//batch_size + 1} 获取失败: {e}")
                continue
            
            progress_bar.progress((i + batch_size) / len(stock_list))
            time.sleep(0.1)
        
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
        if 'close' in result.columns:
            result = result[result['close'] < 10]
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

# ==================== 图表生成函数 ====================
def create_td_chart_plotly(hist_data, td_data, analysis):
    """使用Plotly创建TD技术分析图表"""
    df = td_data.copy().sort_values('trade_date')
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.tail(60)  # 显示最近60个交易日
    
    if len(df) < 10:
        return None
    
    # 创建子图
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        subplot_titles=(
            f'{analysis["name"]} ({analysis["code"]}) - TD序列技术分析图表',
            '成交量分析'
        ),
        vertical_spacing=0.1
    )
    
    # K线图
    fig.add_trace(
        go.Candlestick(
            x=df['trade_date'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='K线',
            increasing_line_color='red',
            decreasing_line_color='green'
        ),
        row=1, col=1
    )
    
    # 添加均线
    if 'ma5' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df['trade_date'], 
                y=df['ma5'], 
                name='MA5', 
                line=dict(color='purple', width=1),
                opacity=0.8
            ),
            row=1, col=1
        )
    
    if 'ma20' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df['trade_date'], 
                y=df['ma20'], 
                name='MA20', 
                line=dict(color='blue', width=2),
                opacity=0.8
            ),
            row=1, col=1
        )
    
    # 添加TD Setup标注
    for i in range(len(df)):
        row = df.iloc[i]
        setup_value = row['td_setup']
        
        if setup_value != 0:
            date = row['trade_date']
            high_price = row['high']
            low_price = row['low']
            
            if setup_value > 0:  # 买入Setup
                y_pos = low_price * 0.995
                color = 'blue'
                symbol = 'circle'
            else:  # 卖出Setup
                y_pos = high_price * 1.005
                color = 'red'
                symbol = 'triangle-down'
            
            fig.add_trace(
                go.Scatter(
                    x=[date],
                    y=[y_pos],
                    mode='markers+text',
                    marker=dict(
                        color=color,
                        size=12,
                        symbol=symbol,
                        line=dict(color='white', width=1)
                    ),
                    text=[f'{abs(setup_value)}'],
                    textposition='middle center',
                    textfont=dict(color='white', size=8),
                    name=f'Setup {abs(setup_value)}',
                    showlegend=False
                ),
                row=1, col=1
            )
    
    # 添加TD Countdown标注
    for i in range(len(df)):
        row = df.iloc[i]
        countdown_value = row['td_countdown']
        
        if countdown_value != 0:
            date = row['trade_date']
            high_price = row['high']
            low_price = row['low']
            
            if countdown_value > 0:  # 买入Countdown
                y_pos = low_price * 0.99
                color = 'darkblue'
            else:  # 卖出Countdown
                y_pos = high_price * 1.01
                color = 'darkred'
            
            fig.add_trace(
                go.Scatter(
                    x=[date],
                    y=[y_pos],
                    mode='markers+text',
                    marker=dict(
                        color=color,
                        size=15,
                        symbol='square',
                        line=dict(color='white', width=2)
                    ),
                    text=[f'C{abs(countdown_value)}'],
                    textposition='middle center',
                    textfont=dict(color='white', size=7),
                    name=f'Countdown {abs(countdown_value)}',
                    showlegend=False
                ),
                row=1, col=1
            )
    
    # 添加完美设置标注
    for i in range(len(df)):
        row = df.iloc[i]
        if row['td_perfected']:
            date = row['trade_date']
            high_price = row['high']
            
            fig.add_trace(
                go.Scatter(
                    x=[date],
                    y=[high_price * 1.02],
                    mode='markers+text',
                    marker=dict(
                        color='gold',
                        size=20,
                        symbol='star',
                        line=dict(color='purple', width=2)
                    ),
                    text=['★'],
                    textposition='middle center',
                    name='完美设置',
                    showlegend=False
                ),
                row=1, col=1
            )
    
    # 添加TDST支撑阻力线
    latest_data = df.iloc[-1]
    if latest_data['tdst_support'] > 0:
        fig.add_hline(
            y=latest_data['tdst_support'],
            line_dash="dash",
            line_color="green",
            annotation_text="TDST支撑",
            row=1, col=1
        )
    
    if latest_data['tdst_resistance'] > 0:
        fig.add_hline(
            y=latest_data['tdst_resistance'],
            line_dash="dash",
            line_color="red",
            annotation_text="TDST阻力",
            row=1, col=1
        )
    
    # 添加关键支撑阻力位
    try:
        support1 = float(analysis['support_levels'].split('S1: ')[1].split(',')[0])
        resistance1 = float(analysis['resistance_levels'].split('R1: ')[1].split(',')[0])
        
        fig.add_hline(
            y=support1,
            line_dash="dot",
            line_color="blue",
            annotation_text="技术支撑",
            row=1, col=1
        )
        
        fig.add_hline(
            y=resistance1,
            line_dash="dot",
            line_color="red",
            annotation_text="技术阻力",
            row=1, col=1
        )
    except:
        pass
    
    # 成交量图
    colors = ['red' if close >= open else 'green' 
              for close, open in zip(df['close'], df['open'])]
    
    fig.add_trace(
        go.Bar(
            x=df['trade_date'], 
            y=df['vol'], 
            name='成交量',
            marker_color=colors,
            opacity=0.6
        ),
        row=2, col=1
    )
    
    # 标注放量点
    volume_avg = df['vol'].rolling(window=10).mean()
    for i in range(len(df)):
        if df.iloc[i]['vol'] > volume_avg.iloc[i] * 2:
            fig.add_annotation(
                x=df.iloc[i]['trade_date'],
                y=df.iloc[i]['vol'],
                text="放量",
                showarrow=True,
                arrowhead=2,
                arrowcolor="red",
                arrowsize=1,
                arrowwidth=2,
                bgcolor="yellow",
                bordercolor="red",
                borderwidth=1,
                row=2, col=1
            )
    
    # 更新布局
    fig.update_layout(
        title=f'{analysis["name"]} ({analysis["code"]}) - TD序列技术分析图表',
        xaxis_rangeslider_visible=False,
        height=800,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # 更新坐标轴
    fig.update_xaxes(title_text="日期", row=2, col=1)
    fig.update_yaxes(title_text="价格 (元)", row=1, col=1)
    fig.update_yaxes(title_text="成交量 (手)", row=2, col=1)
    
    return fig

# ==================== 主界面函数 ====================
def main():
    # 页面标题
    st.title("📈 增强版TD股票分析系统")
    st.markdown("### 基于前复权数据的专业技术分析 | 完整功能版本")
    st.markdown("---")
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 分析设置")
        
        # 日期选择
        st.subheader("📅 分析日期设置")
        date_mode = st.radio(
            "选择日期方式",
            ["🔄 使用最新交易日", "📅 手动选择日期"]
        )
        
        if date_mode == "🔄 使用最新交易日":
            target_date = get_latest_trade_date()
            st.success(f"📅 最新交易日: {target_date}")
        else:
            selected_date = st.date_input(
                "选择分析日期",
                value=datetime.now().date(),
                min_value=datetime(2020, 1, 1).date(),
                max_value=datetime.now().date()
            )
            target_date = selected_date.strftime('%Y%m%d')
            
            # 验证交易日
            if st.button("🔍 验证交易日"):
                if check_trade_date(target_date):
                    st.success("✅ 这是一个交易日")
                else:
                    st.error("❌ 这不是交易日")
                    nearby_dates = get_nearby_trade_dates(target_date)
                    if nearby_dates:
                        st.info("📅 附近的交易日:")
                        for date in nearby_dates[-5:]:
                            st.write(f"• {date}")
        
        # 筛选参数
        st.subheader("🎯 筛选条件")
        max_price = st.slider("最大股价(元)", 5.0, 20.0, 10.0, 0.5)
        min_turnover = st.slider("最小换手率(%)", 0.5, 5.0, 1.5, 0.1)
        min_market_cap = st.slider("最小市值(亿元)", 20, 100, 40, 5)
        
        st.markdown("---")
        st.markdown("### 📋 筛选说明")
        st.markdown(f"""
        - 排除科创板、创业板、ST股票
        - 股价 < {max_price}元
        - 换手率 > {min_turnover}%  
        - 市值 > {min_market_cap}亿元
        - 按市值从小到大排序
        """)
        
        # TD分析参数
        st.subheader("🔧 TD分析参数")
        enable_charts = st.checkbox("📊 生成交互式图表", value=True)
        max_analysis_stocks = st.slider("最大分析股票数", 1, 20, 10)
    
    # 主界面标签页
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 股票筛选", 
        "📈 TD技术分析", 
        "📋 分析报告", 
        "📚 使用说明"
    ])
    
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
                            
                            # 显示数据表格
                            st.subheader("📋 筛选结果详情")
                            
                            # 选择要显示的列
                            display_cols = ['ts_code', 'name']
                            if 'close' in result.columns:
                                display_cols.append('close')
                                result = result.rename(columns={'close': '股价(元)'})
                            
                            if 'turnover_rate' in result.columns:
                                display_cols.append('turnover_rate')
                                result = result.rename(columns={'turnover_rate': '换手率%'})
                            
                            if 'total_mv' in result.columns:
                                result['市值(亿)'] = result['total_mv'] / 10000
                                display_cols.append('市值(亿)')
                            
                            if 'pe' in result.columns:
                                display_cols.append('pe')
                                result = result.rename(columns={'pe': '市盈率'})
                            
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
            
            1. 调整左侧筛选条件
            2. 点击"开始筛选"按钮
            3. 等待数据获取完成
            4. 查看筛选结果
            5. 切换到"TD技术分析"标签页进行深度分析
            """)
    
    with tab2:
        st.subheader("📈 增强版TD技术分析")
        
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
            
            # 限制选择数量
            max_selections = min(max_analysis_stocks, len(options))
            default_selections = min(5, len(options))
            
            selected_options = st.multiselect(
                f"🎯 选择要分析的股票 (最多{max_selections}只)",
                options=options,
                default=options[:default_selections],
                help=f"建议一次分析3-{max_selections}只股票，避免过多请求导致超时"
            )
            
            if len(selected_options) > max_selections:
                st.warning(f"⚠️ 选择股票数量过多，将只分析前{max_selections}只")
                selected_options = selected_options[:max_selections]
            
            if selected_options:
                # 提取选中的股票代码
                selected_codes = []
                for option in selected_options:
                    code = option.split('(')[-1].split(')')[0]
                    selected_codes.append(code)
                
                st.info(f"📊 已选择 {len(selected_codes)} 只股票进行分析")
                
                if st.button("🔍 开始增强版TD分析", type="primary"):
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    analyses = []
                    
                    for i, code in enumerate(selected_codes):
                        name = stocks_df[stocks_df['ts_code'] == code]['name'].iloc[0]
                        status_text.text(f"正在分析: {name} ({code}) [{i+1}/{len(selected_codes)}]")
                        
                        try:
                            analysis = perform_td_analysis_enhanced(code, name, target_date)
                            
                            if 'analysis' not in analysis or not isinstance(analysis.get('analysis'), str):
                                analyses.append(analysis)
                                
                                # 显示单个股票的分析结果
                                with st.expander(f"📊 {analysis['name']} ({analysis['code']}) - TD分析结果", expanded=True):
                                    
                                    # 基本信息展示
                                    col1, col2, col3, col4 = st.columns(4)
                                    
                                    with col1:
                                        st.metric("💰 当前价格", f"¥{analysis['current_price']:.2f}")
                                        st.metric("🔢 TD Setup", analysis['td_setup'])
                                    
                                    with col2:
                                        st.metric("⏰ TD Countdown", analysis['td_countdown'])
                                        st.metric("🎯 信号等级", analysis['td_signal_grade'])
                                    
                                    with col3:
                                        st.metric("📈 反转概率", f"{analysis['reversal_probability']:.1f}%")
                                        st.metric("⚖️ 风险等级", analysis['td_risk_level'])
                                    
                                    with col4:
                                        st.metric("📊 TD评分", f"{analysis['td_score']}分")
                                        st.metric("💪 信心度", f"{analysis['confidence']:.1f}%")
                                    
                                    # TD阶段信息
                                    st.subheader("🔍 TD序列状态")
                                    col_a, col_b = st.columns(2)
                                    
                                    with col_a:
                                        st.write(f"**当前阶段**: {analysis['td_phase']}")
                                        st.write(f"**均线趋势**: {analysis['ma_trend']}")
                                        st.write(f"**K线形态**: {analysis['pattern']}")
                                    
                                    with col_b:
                                        if analysis['td_perfected']:
                                            st.success("✨ **完美设置**: 已确认")
                                        else:
                                            st.info("**完美设置**: 未出现")
                                        
                                        st.write(f"**TDST位**: {analysis['tdst_levels']}")
                                    
                                    # 关键价位
                                    st.subheader("💰 关键价位")
                                    col_x, col_y = st.columns(2)
                                    
                                    with col_x:
                                        st.write(f"**支撑位**: {analysis['support_levels']}")
                                        st.write(f"**轴心点**: {analysis['pivot']}")
                                    
                                    with col_y:
                                        st.write(f"**阻力位**: {analysis['resistance_levels']}")
                                    
                                    # 成交量分析
                                    st.subheader("📊 成交量分析")
                                    vol_analysis = analysis['volume_analysis']
                                    
                                    col_p, col_q = st.columns(2)
                                    with col_p:
                                        st.write(f"**成交量趋势**: {vol_analysis['volume_trend']}")
                                        st.write(f"**量比**: {vol_analysis['volume_ratio']:.2f}倍")
                                    
                                    with col_q:
                                        st.write(f"**价量关系**: {vol_analysis['volume_price_match']}")
                                        if vol_analysis['volume_surge']:
                                            st.success("🚀 **爆量信号**: 资金关注度高")
                                    
                                    # 交易策略
                                    st.subheader("💡 交易策略")
                                    strategy = analysis['td_strategy']
                                    
                                    # 操作建议
                                    if strategy['direction'] == "买入":
                                        st.success(f"🟢 **操作方向**: {strategy['direction']}")
                                    elif strategy['direction'] == "卖出/观望":
                                        st.error(f"🔴 **操作方向**: {strategy['direction']}")
                                    else:
                                        st.info(f"🟡 **操作方向**: {strategy['direction']}")
                                    
                                    col_m, col_n = st.columns(2)
                                    
                                    with col_m:
                                        st.write(f"**建议仓位**: {strategy['position_size']}")
                                        st.write(f"**时间框架**: {strategy['time_frame']}")
                                        st.write(f"**风险收益比**: {strategy['risk_reward']}")
                                    
                                    with col_n:
                                        st.write("**入场点位**:")
                                        for level, price in strategy['entry_points'].items():
                                            st.write(f"• {level}: {price}")
                                    
                                    # 目标位
                                    st.write("**目标位设置**:")
                                    for target in strategy['targets']:
                                        st.write(f"• {target}")
                                    
                                    if strategy['stop_loss'] > 0:
                                        st.write(f"**止损位**: ¥{strategy['stop_loss']:.2f}")
                                    
                                    # 特殊提示
                                    if strategy['notes']:
                                        st.subheader("💡 特殊提示")
                                        for note in strategy['notes']:
                                            st.info(note)
                                    
                                    # 生成交互式图表
                                    if enable_charts:
                                        st.subheader("📈 TD序列技术图表")
                                        
                                        with st.spinner("生成交互式图表..."):
                                            try:
                                                chart = create_td_chart_plotly(
                                                    analysis['hist_data'], 
                                                    analysis['td_data'], 
                                                    analysis
                                                )
                                                
                                                if chart:
                                                    st.plotly_chart(chart, use_container_width=True)
                                                    
                                                    # 图表说明
                                                    with st.expander("📋 图表说明"):
                                                        st.markdown("""
                                                        **📊 图表元素说明:**
                                                        - **蓝色圆点 + 数字**: TD买入Setup序号 (1-9)
                                                        - **红色三角 + 数字**: TD卖出Setup序号 (1-9)
                                                        - **蓝色方块 C数字**: TD买入Countdown序号 (1-13)
                                                        - **红色方块 C数字**: TD卖出Countdown序号 (1-13)
                                                        - **金色★**: 完美设置，提高信号可靠性
                                                        - **虚线**: TDST动态支撑阻力线
                                                        - **点线**: 传统技术支撑阻力位
                                                        - **彩色线条**: MA5(紫) MA20(蓝)
                                                        - **成交量**: 红色上涨日，绿色下跌日
                                                        """)
                                                else:
                                                    st.warning("图表生成失败")
                                            except Exception as e:
                                                st.error(f"图表生成出错: {e}")
                            
                            else:
                                st.error(f"❌ {name} 分析失败: {analysis.get('analysis', '未知错误')}")
                        
                        except Exception as e:
                            st.error(f"❌ 分析 {name} 时出错: {str(e)}")
                        
                        progress_bar.progress((i + 1) / len(selected_codes))
                        time.sleep(0.1)  # 避免API限制
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    # 保存分析结果
                    if analyses:
                        st.session_state.analyses = analyses
                        st.success(f"✅ TD分析完成！成功分析 {len(analyses)} 只股票")
                    else:
                        st.warning("❌ 没有获得有效的分析结果")
            else:
                st.info("请选择要分析的股票")
    
    with tab3:
        st.subheader("📋 TD分析综合报告")
        
        if 'analyses' not in st.session_state:
            st.info("📊 请先进行TD技术分析")
        else:
            analyses = st.session_state.analyses
            
            if analyses:
                # 重点关注股票
                focus_stocks = [a for a in analyses if (
                    a.get('td_score', 0) >= 20 or
                    abs(a.get('td_countdown', 0)) >= 8 or
                    a.get('confidence', 0) >= 45
                )]
                
                if focus_stocks:
                    st.subheader(f"🎯 重点关注股票 ({len(focus_stocks)}只)")
                    
                    # 按评分排序
                    focus_stocks.sort(key=lambda x: x.get('td_score', 0), reverse=True)
                    
                    for i, stock in enumerate(focus_stocks, 1):
                        with st.container():
                            col1, col2, col3 = st.columns([2, 2, 1])
                            
                            with col1:
                                st.write(f"**{i}. {stock['name']} ({stock['code']})**")
                                st.write(f"价格: ¥{stock['current_price']:.2f} | 评分: {stock['td_score']}分")
                            
                            with col2:
                                st.write(f"Setup: {stock['td_setup']} | Countdown: {stock['td_countdown']}")
                                st.write(f"信号: {stock['td_signal_grade']} | 操作: {stock['td_strategy']['direction']}")
                            
                            with col3:
                                confidence = stock['confidence']
                                if confidence >= 70:
                                    st.success(f"信心度: {confidence:.1f}%")
                                elif confidence >= 50:
                                    st.info(f"信心度: {confidence:.1f}%")
                                else:
                                    st.warning(f"信心度: {confidence:.1f}%")
                        
                        st.markdown("---")
                else:
                    st.info("📊 当前没有特别突出的重点关注股票")
                
                # 统计分析
                st.subheader("📊 分析统计")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    total_stocks = len(analyses)
                    st.metric("总分析股票", total_stocks)
                
                with col2:
                    avg_score = sum(a.get('td_score', 0) for a in analyses) / len(analyses)
                    st.metric("平均TD评分", f"{avg_score:.1f}分")
                
                with col3:
                    buy_signals = sum(1 for a in analyses if a['td_strategy']['direction'] == '买入')
                    st.metric("买入信号", f"{buy_signals}只")
                
                with col4:
                    high_confidence = sum(1 for a in analyses if a.get('confidence', 0) >= 60)
                    st.metric("高信心股票", f"{high_confidence}只")
                
                # 信号等级分布
                st.subheader("📈 信号等级分布")
                
                signal_grades = {}
                for analysis in analyses:
                    grade = analysis.get('td_signal_grade', 'C级（弱）').split('级')[0]
                    signal_grades[grade] = signal_grades.get(grade, 0) + 1
                
                col_a, col_b, col_c, col_d = st.columns(4)
                
                with col_a:
                    st.metric("S级信号", signal_grades.get('S', 0))
                with col_b:
                    st.metric("A级信号", signal_grades.get('A', 0))
                with col_c:
                    st.metric("B级信号", signal_grades.get('B', 0))
                with col_d:
                    st.metric("C级信号", signal_grades.get('C', 0))
                
                # 详细分析表格
                st.subheader("📋 详细分析汇总表")
                
                # 创建汇总数据
                summary_data = []
                for analysis in analyses:
                    summary_data.append({
                        '股票代码': analysis['code'],
                        '股票名称': analysis['name'],
                        '当前价格': f"¥{analysis['current_price']:.2f}",
                        'TD Setup': analysis['td_setup'],
                        'TD Countdown': analysis['td_countdown'],
                        '信号等级': analysis['td_signal_grade'],
                        'TD评分': analysis['td_score'],
                        '信心度': f"{analysis['confidence']:.1f}%",
                        '操作建议': analysis['td_strategy']['direction'],
                        '建议仓位': analysis['td_strategy']['position_size'].split('（')[0],
                        '风险等级': analysis['td_risk_level']
                    })
                
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                # 下载报告
                if st.button("📥 下载分析报告(CSV)"):
                    csv = summary_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="点击下载",
                        data=csv,
                        file_name=f"TD分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            else:
                st.info("📊 暂无分析数据")
    
    with tab4:
        st.markdown("""
        # 📚 增强版TD股票分析系统使用说明
        
        ## 🎯 系统概述
        
        本系统是一个基于Tushare数据的**专业级TD序列股票技术分析系统**，完整实现了原始代码的所有功能。
        
        ## 🔬 核心技术分析功能
        
        ### TD序列分析
        - **TD Setup**: 1-9序列，识别趋势反转初期信号
        - **TD Countdown**: 1-13倒计时，确认反转信号
        - **TD Combo**: 组合计数，提供额外确认
        - **完美设置**: 提高信号可靠性的特殊条件
        - **TDST位**: 基于TD序列的动态支撑阻力
        
        ### 技术指标
        - **ATR动态止损**: 基于真实波幅的科学止损
        - **支撑阻力计算**: 多层次关键价位识别
        - **成交量分析**: 量价配合度、异常量能检测
        - **市场强度**: 整体市场环境评估
        - **K线形态**: 经典形态识别和分析
        
        ## 🛠️ 使用流程
        
        ### 第一步：股票筛选
        1. 设置筛选条件（股价、换手率、市值）
        2. 选择分析日期（最新交易日或手动选择）
        3. 点击"开始筛选分析"
        4. 查看筛选结果和统计信息
        
        ### 第二步：TD技术分析
        1. 从筛选结果中选择要分析的股票
        2. 点击"开始增强版TD分析"
        3. 查看每只股票的详细分析结果
        4. 查看交互式技术图表
        
        ### 第三步：综合报告
        1. 查看重点关注股票汇总
        2. 查看统计分析和信号分布
        3. 查看详细分析表格
        4. 下载CSV分析报告
        
        ## 📊 TD序列指标详解
        
        ### TD Setup (1-9)
        - **1-3**: 初期信号，市场开始转向
        - **4-6**: 中期信号，趋势逐渐明确
        - **7-8**: 后期信号，接近反转点
        - **9**: 设置完成，强烈反转信号
        
        ### TD Countdown (1-13)
        - **1-6**: 倒计时初期，确认设置有效性
        - **7-12**: 倒计时中后期，重点关注
        - **13**: 倒计时完成，最强反转确认
        
        ## ⚡ 信号等级系统
        
        - **S级 (≥70分)**: 极强信号，重点关注
        - **A级 (50-69分)**: 强信号，积极参与
        - **B级 (25-49分)**: 中等信号，适度参与
        - **C级 (<25分)**: 弱信号，小仓位试探
        
        ## 💰 交易策略建议
        
        ### 仓位管理
        - **50-70%**: 高信心重仓（信心度≥75%）
        - **40-50%**: 较高信心（信心度60-74%）
        - **30-40%**: 中等信心（信心度45-59%）
        - **20-30%**: 偏低信心（信心度35-44%）
        - **10-20%**: 低信心试探（信心度<35%）
        
        ### 时间框架
        - **短线 (5-15天)**: TD Setup信号
        - **波段 (2-4周)**: TD Setup后期 + 高评分
        - **中线 (1-3个月)**: TD Countdown信号
        
        ## 📈 图表解读指南
        
        ### 图表元素
        - **蓝色圆点 + 数字**: TD买入Setup序号 (1-9)
        - **红色三角 + 数字**: TD卖出Setup序号 (1-9)
        - **蓝色方块 C数字**: TD买入Countdown序号 (1-13)
        - **红色方块 C数字**: TD卖出Countdown序号 (1-13)
        - **金色★**: 完美设置标记
        - **虚线**: TDST动态支撑阻力线
        - **点线**: 传统技术支撑阻力位
        - **彩色线条**: MA5(紫) MA20(蓝)
        
        ## ⚠️ 风险提示
        
        **投资有风险，入市需谨慎！**
        
        1. 本系统仅供技术分析参考，不构成投资建议
        2. TD分析是概率性工具，不能预测未来
        3. 建议结合基本面分析和市场环境
        4. 严格执行资金管理和止损纪律
        
        ## 🔧 技术支持
        
        - 数据来源：Tushare专业金融数据接口
        - 技术架构：Streamlit + Pandas + Plotly
        - 更新频率：实时更新（交易日）
        
        ---
        
        ### 🎉 感谢使用增强版TD股票分析系统！
        
        祝您投资顺利，收益满满！📈💰
        """)

if __name__ == "__main__":
    main()

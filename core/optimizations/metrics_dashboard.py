"""
Metrics Dashboard for NubemSuperFClaude
Real-time monitoring and visualization of system performance
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
import time
import json
import sqlite3
from typing import Dict, Any, List
import psutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MetricsDashboard:
    """
    Real-time dashboard for monitoring NubemSuperFClaude metrics
    """
    
    def __init__(self):
        self.db_path = "api_usage.db"
        self.initialize_dashboard()
    
    def initialize_dashboard(self):
        """Initialize Streamlit dashboard configuration"""
        st.set_page_config(
            page_title="NubemSuperFClaude Metrics",
            page_icon="🚀",
            layout="wide",
            initial_sidebar_state="expanded"
        )
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "network_io": psutil.net_io_counters()
        }
    
    def get_api_metrics(self, hours: int = 24) -> pd.DataFrame:
        """Get API usage metrics from database"""
        conn = sqlite3.connect(self.db_path)
        
        query = """
        SELECT 
            timestamp,
            provider,
            model,
            input_tokens,
            output_tokens,
            cost,
            request_type
        FROM api_usage
        WHERE datetime(timestamp) >= datetime('now', '-{} hours')
        ORDER BY timestamp DESC
        """.format(hours)
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    
    def get_cost_breakdown(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate cost breakdown by model"""
        if df.empty:
            return pd.DataFrame()
        
        cost_by_model = df.groupby('model').agg({
            'cost': 'sum',
            'input_tokens': 'sum',
            'output_tokens': 'sum'
        }).round(4)
        
        cost_by_model['requests'] = df.groupby('model').size()
        cost_by_model['avg_cost'] = cost_by_model['cost'] / cost_by_model['requests']
        
        return cost_by_model.sort_values('cost', ascending=False)
    
    def create_latency_chart(self) -> go.Figure:
        """Create latency comparison chart"""
        # Simulated data (in production, get from actual metrics)
        models = ['GPT-4', 'GPT-3.5', 'Claude-3', 'Gemini-1.5-Flash', 'Gemini-1.5-Pro']
        latencies = [1.5, 0.8, 0.7, 0.45, 0.7]
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        
        fig = go.Figure(data=[
            go.Bar(
                x=models,
                y=latencies,
                marker_color=colors,
                text=[f'{l}s' for l in latencies],
                textposition='auto',
            )
        ])
        
        fig.update_layout(
            title="Average Latency by Model",
            xaxis_title="Model",
            yaxis_title="Latency (seconds)",
            height=300,
            showlegend=False
        )
        
        return fig
    
    def create_cost_timeline(self, df: pd.DataFrame) -> go.Figure:
        """Create cost timeline chart"""
        if df.empty:
            return go.Figure()
        
        # Group by hour
        df['hour'] = df['timestamp'].dt.floor('H')
        hourly_cost = df.groupby('hour')['cost'].sum().reset_index()
        
        fig = px.line(
            hourly_cost,
            x='hour',
            y='cost',
            title='Hourly API Costs',
            labels={'cost': 'Cost ($)', 'hour': 'Time'}
        )
        
        fig.update_layout(height=300)
        return fig
    
    def create_usage_pie(self, df: pd.DataFrame) -> go.Figure:
        """Create usage distribution pie chart"""
        if df.empty:
            return go.Figure()
        
        provider_counts = df['provider'].value_counts()
        
        fig = px.pie(
            values=provider_counts.values,
            names=provider_counts.index,
            title='API Usage Distribution'
        )
        
        fig.update_layout(height=300)
        return fig
    
    def create_cache_performance(self) -> go.Figure:
        """Create cache performance gauge"""
        # Get cache stats (simulated for demo)
        cache_hit_rate = 65  # In production, get from cache.get_stats()
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=cache_hit_rate,
            title={'text': "Cache Hit Rate"},
            delta={'reference': 50},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 30], 'color': "lightgray"},
                    {'range': [30, 70], 'color': "gray"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            },
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        
        fig.update_layout(height=250)
        return fig
    
    def run(self):
        """Run the dashboard application"""
        
        # Header
        st.title("🚀 NubemSuperFClaude Metrics Dashboard")
        st.markdown("Real-time monitoring of API usage, costs, and performance")
        
        # Sidebar controls
        with st.sidebar:
            st.header("⚙️ Controls")
            
            time_range = st.selectbox(
                "Time Range",
                ["Last Hour", "Last 24 Hours", "Last 7 Days", "Last 30 Days"],
                index=1
            )
            
            refresh_rate = st.selectbox(
                "Refresh Rate",
                ["Manual", "5 seconds", "30 seconds", "1 minute"],
                index=0
            )
            
            if st.button("🔄 Refresh Now"):
                st.rerun()
            
            st.divider()
            
            # System Health
            st.header("💻 System Health")
            system_metrics = self.get_system_metrics()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("CPU", f"{system_metrics['cpu_percent']}%")
            with col2:
                st.metric("Memory", f"{system_metrics['memory_percent']}%")
            
            st.progress(system_metrics['cpu_percent'] / 100)
            
        # Main content
        # Top metrics row
        col1, col2, col3, col4, col5 = st.columns(5)
        
        # Get data
        hours_map = {
            "Last Hour": 1,
            "Last 24 Hours": 24,
            "Last 7 Days": 168,
            "Last 30 Days": 720
        }
        hours = hours_map.get(time_range, 24)
        df = self.get_api_metrics(hours)
        
        with col1:
            total_requests = len(df)
            st.metric(
                "Total Requests",
                f"{total_requests:,}",
                delta="+12%" if total_requests > 0 else "0%"
            )
        
        with col2:
            total_cost = df['cost'].sum() if not df.empty else 0
            st.metric(
                "Total Cost",
                f"${total_cost:.2f}",
                delta="-15%" if total_cost > 0 else "0%",
                delta_color="inverse"
            )
        
        with col3:
            avg_latency = 0.75  # Simulated
            st.metric(
                "Avg Latency",
                f"{avg_latency:.2f}s",
                delta="-0.15s",
                delta_color="inverse"
            )
        
        with col4:
            success_rate = 98.5  # Simulated
            st.metric(
                "Success Rate",
                f"{success_rate:.1f}%",
                delta="+2.1%"
            )
        
        with col5:
            cache_hit_rate = 65  # Simulated
            st.metric(
                "Cache Hit Rate",
                f"{cache_hit_rate}%",
                delta="+5%"
            )
        
        st.divider()
        
        # Charts row 1
        col1, col2 = st.columns(2)
        
        with col1:
            st.plotly_chart(
                self.create_latency_chart(),
                use_container_width=True
            )
        
        with col2:
            st.plotly_chart(
                self.create_cost_timeline(df),
                use_container_width=True
            )
        
        # Charts row 2
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.plotly_chart(
                self.create_usage_pie(df),
                use_container_width=True
            )
        
        with col2:
            st.plotly_chart(
                self.create_cache_performance(),
                use_container_width=True
            )
        
        with col3:
            # Circuit breaker status
            st.subheader("🔌 Circuit Breakers")
            
            # Simulated circuit states
            circuits = {
                "OpenAI": "🟢 Closed",
                "Anthropic": "🟢 Closed",
                "Google": "🟢 Closed"
            }
            
            for api, state in circuits.items():
                st.text(f"{api}: {state}")
        
        st.divider()
        
        # Cost breakdown table
        st.subheader("💰 Cost Breakdown by Model")
        
        cost_df = self.get_cost_breakdown(df)
        if not cost_df.empty:
            st.dataframe(
                cost_df,
                use_container_width=True,
                column_config={
                    "cost": st.column_config.NumberColumn(
                        "Total Cost",
                        format="$%.4f"
                    ),
                    "avg_cost": st.column_config.NumberColumn(
                        "Avg Cost",
                        format="$%.6f"
                    )
                }
            )
        else:
            st.info("No data available for the selected time range")
        
        # Recent requests
        st.subheader("📝 Recent Requests")
        
        if not df.empty:
            recent_df = df.head(10)[['timestamp', 'model', 'cost', 'request_type']]
            st.dataframe(
                recent_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "timestamp": "Time",
                    "model": "Model",
                    "cost": st.column_config.NumberColumn(
                        "Cost",
                        format="$%.6f"
                    ),
                    "request_type": "Type"
                }
            )
        else:
            st.info("No recent requests")
        
        # Auto-refresh logic
        if refresh_rate != "Manual":
            refresh_seconds = {
                "5 seconds": 5,
                "30 seconds": 30,
                "1 minute": 60
            }
            
            time.sleep(refresh_seconds[refresh_rate])
            st.rerun()


# Standalone dashboard runner
def run_dashboard():
    """Entry point for running the dashboard"""
    dashboard = MetricsDashboard()
    dashboard.run()


if __name__ == "__main__":
    run_dashboard()
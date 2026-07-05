#!/bin/bash
# 执行每日收盘分析

# 加载用户环境变量（确保 MX_APIKEY 等可用）
# 注意：先临时关闭 set -e，因为 .zshrc 包含 zsh 专属命令（autoload 等）
# 在 bash 下 source 会触发 command not found，set -e 状态下即使有 || true
# 某些 bash 版本仍会退出，故此处显式 set +e
set +e
source /Users/leenzhou/.zshrc 2>/dev/null
set -e

# 配置路径
SCRIPT_DIR="/Users/leenzhou/.hermes/skills/mx-selfselect/scripts"
PROJECT_DIR="/Users/leenzhou/daily_stock_analysis"
LOG_FILE="$PROJECT_DIR/logs/daily_analysis.log"

# 创建日志目录
mkdir -p "$(dirname "$LOG_FILE")"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "========== 开始执行每日收盘分析 =========="

# 运行mx_self_select.py获取自选股列表
OUTPUT=$(cd "$SCRIPT_DIR" && python3 mx_self_select.py query 2>&1)

# 检查是否成功获取自选股
if echo "$OUTPUT" | grep -q "股票代码"; then
    # 提取股票代码（从表格中提取第一列，跳过表头和分隔线）
    STOCK_CODES=$(echo "$OUTPUT" | grep -E '^[0-9]' | awk '{print $1}' | tr '\n' ',' | sed 's/,$//')
    
    log "获取到自选股代码: $STOCK_CODES"
    
    # 更新.env文件中的STOCK_LIST
    if grep -q "^STOCK_LIST=" "$PROJECT_DIR/.env"; then
        sed -i '' "s/^STOCK_LIST=.*/STOCK_LIST=$STOCK_CODES/" "$PROJECT_DIR/.env"
    else
        echo "STOCK_LIST=$STOCK_CODES" >> "$PROJECT_DIR/.env"
    fi
    
    # 执行分析脚本
    log "开始执行分析脚本..."
    cd "$PROJECT_DIR"
    
    # 使用虚拟环境执行
    if .venv/bin/python main.py --stocks "$STOCK_CODES" 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ 分析执行完成"
        echo "分析执行完成"
    else
        log "❌ 分析执行失败"
        echo "分析执行失败，请查看日志: $LOG_FILE"
        exit 1
    fi
else
    log "❌ 获取自选股列表失败"
    log "输出: $OUTPUT"
    echo "获取自选股列表失败，请查看日志: $LOG_FILE"
    exit 1
fi

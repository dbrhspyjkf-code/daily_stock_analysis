# 📊 自选股今日分析报告（{{日期}}）
---
## 📝 自选股列表（共{{数量}}只）
{{#each stocks}}
{{this.index}}. {{this.code}} {{this.name}} | 最新价{{this.price}}元 | 涨跌幅{{this.change}}%
{{/each}}
---
## 🔍 单只股票核心分析
{{#each stocks}}
### {{this.index}}. {{this.name}}({{this.code}})
- **基本面支撑**: {{this.basic_analysis}}
- **MACD信号**: {{this.macd_analysis}}
- **近一周资金流向**: {{this.fund_analysis}}
- **融资融券趋势**: {{this.margin_analysis}}
- **核心洞察**: {{this.insight}} **{{this.suggestion}}**

{{/each}}
---
## 🎯 整体配置建议
✅ **优先持有**: {{hold_list}}（科技成长赛道，景气度高）
⚠️ **观望等待**: {{wait_list}}（周期底部/行业不确定性大）
💡 **逢低布局**: {{buy_list}}（周期复苏预期，估值低）
---
> 数据来源：东方财富、妙想金融数据，分析仅供参考，不构成投资建议。
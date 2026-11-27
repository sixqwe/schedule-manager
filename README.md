# 课表总览 · Schedule Manager

把教务课表导入后，按周生成多人总览。适合班级、社团或办公室贴在局域网里查看：谁在什么时间、哪个教室上课，一页看清。

## 功能

- 导入课表后按教学周筛选
- 多人课表合并总览，按人/按天查看
- 支持导出 `calendar.ics`，可订阅到系统日历
- 只读身份与可维护身份分离，避免误改数据
- 单文件 Python 服务 + 单页前端，SQLite 本地存储

## 运行

需要 Python 3.10+：

```bash
python3 server.py
```

默认端口 `17860`，打开 <http://localhost:17860/>。

首次启动会在同目录生成：

- `data.db`：课表与人员数据，已加入 `.gitignore`
- `.session_key`：会话签名密钥，已加入 `.gitignore`
- `password.txt`：可选，写入后作为整体维护口令

默认口令是 `change-me`，部署前请务必在 `password.txt` 里换成自己的口令，或修改 `server.py` 中的 `DEFAULT_PASSWORD`。

## 数据与隐私

课表、姓名、学号属于个人数据。仓库只保留代码和脱敏样本，不包含 `data.db`、`sources/` 里的真实课表或导出文件。公开部署前请先确认所在学校的数据使用规定。

## 文件

- `server.py`：导入解析、鉴权、课表接口与 ICS 导出
- `index.html`：总览页面
- `gen_test.py`：生成脱敏测试数据
- `v6/`：内置的 INKFLAKE 页面样式

## 许可

MIT License，见 [LICENSE](LICENSE)。

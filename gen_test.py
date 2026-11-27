# -*- coding: utf-8 -*-
"""造几份测试课表并导入"""
import os, json, uuid, urllib.request

BASE = "http://127.0.0.1:17860"

def post_multipart(url, fields, files):
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fname, fdata, ctype) in files.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
        body += fdata + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def make_html(name, courses):
    """courses: list of (course_name, time_place)"""
    rows = ""
    for cname, tplace in courses:
        rows += f"""<tr>
<td style="text-align:center;">000001</td>
<td style="text-align:left;">测试班</td>
<td style="text-align:left;">[0000]{cname}</td>
<td style="text-align:right;">32</td>
<td style="text-align:right;">2.0</td>
<td style="text-align:center;">初修</td>
<td style="text-align:left;">[000001]张老师</td>
<td style="text-align:center;">选中</td>
<td style="text-align:center;">否</td>
<td style="text-align:center;">否</td>
<td style="text-align:left;">{tplace}</td>
<td style="text-align:left;"></td>
</tr>"""
    return f"""<html><head><meta charset="GBK"></head><body>
<table><tbody>{rows}</tbody></table>
</body></html>"""

# 4个人不同风格
people = {
    "李华": [  # 满课型：周一到周五每天早中晚都有
        ("高等数学", "1-16周 一[1-2] JX1#101(80)；1-16周 三[1-2] JX1#101(80)"),
        ("大学语文", "1-16周 一[3-4] JX1#102(80)；1-16周 四[3-4] JX1#102(80)"),
        ("马克思原理", "1-16周 二[1-2] JX1#103(100)；1-16周 五[1-2] JX1#103(100)"),
        ("程序设计", "1-16周 二[3-4] JX1#104(80)；1-16周 五[3-4] JX1#104(80)"),
        ("体育", "1-16周 三[3-4] 公共体育场(999)"),
        ("思想道德", "1-16周 四[1-2] JX1#105(80)"),
        ("心理健康", "1-16周 一[5-6] JX1#106(80)；1-16周 三[5-6] JX1#106(80)"),
        ("形势与政策", "1-16周 二[5-6] JX1#107(80)；1-16周 四[5-6] JX1#107(80)"),
        ("专业导论", "1-16周 五[5-6] JX1#108(80)"),
        ("晚自修", "1-16周 一[7-8] JX1#109(80)；1-16周 三[7-8] JX1#109(80)"),
    ],
    "王芳": [  # 课少型：只有周二周四有课，其他天全空
        ("英语听力", "1-16周 二[1-2] JX1#201(60)"),
        ("英语口语", "1-16周 二[3-4] JX1#202(60)"),
        ("计算机基础", "1-16周 四[1-2] JX1#203(60)；1-16周 四[3-4] JX1#203(60)"),
        ("军事理论", "1-16周 二[5-6] JX1#204(80)"),
    ],
    "张伟": [  # 晚课+周末型：晚上和周六有课
        ("专业核心课", "1-16周 一[7-8] JX1#301(80)；1-16周 三[7-8] JX1#301(80)"),
        ("选修课", "1-16周 二[9-10] JX1#302(80)；1-16周 四[9-10] JX1#302(80)"),
        ("实验课", "1-16周 五[7-8] 实验楼#1(60)"),
        ("周六实验", "1-16周 六[1-2] 实验楼#2(60)；1-16周 六[3-4] 实验楼#2(60)"),
        ("周日补习", "1-16周 日[1-2] JX1#303(60)"),
    ],
    "刘洋": [  # 实验课跨块型：有连续4节大实验
        ("普通化学实验", "1-16周 三[5-8] 化学实验室(60)"),
        ("大学物理", "1-16周 一[1-2] JX1#401(100)；1-16周 二[1-2] JX1#401(100)"),
        ("线性代数", "1-16周(双) 五[3-4] JX1#402(80)"),
        ("生物导论", "1-16周 四[7-8] JX1#403(80)"),
        ("通识选修", "1-16周 六[3-4] JX1#404(80)"),
    ],
}

os.makedirs("test_data", exist_ok=True)
for name, courses in people.items():
    html = make_html(name, courses)
    path = f"test_data/{name}.html"
    with open(path, "wb") as f:
        f.write(html.encode("gbk"))
    # 导入
    with open(path, "rb") as f:
        fdata = f.read()
    r = post_multipart(BASE + "/api/import", {"name": name}, {"file": (f"{name}.html", fdata, "application/octet-stream")})
    print(name, "->", r)

# 列出所有人
with urllib.request.urlopen(BASE + "/api/persons") as resp:
    persons = json.loads(resp.read().decode())
print("\n所有人:", [p["name"] for p in persons])

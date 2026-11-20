"""回归测试：biz 提取必须拒绝 ${window.biz} 等占位符，只接受合法 base64 __biz"""
from core import seed

REAL_BIZ = "MzA5MDMwMTIyNQ=="

print("=" * 55)
print("TEST 1: HTML 同时含占位符和真实 biz → 必须取真实值")
html1 = """
<script>
var appmsg = { biz: "${window.biz}", uin: "${window.uin}" };
var biz = "MzA5MDMwMTIyNQ==" || "";
</script>
"""
got = seed.extract_biz_from_html(html1)
print("  got:", got)
assert got == REAL_BIZ, f"期望 {REAL_BIZ}，得到 {got}"

print("=" * 55)
print("TEST 2: HTML 只有占位符 → 必须返回 None，绝不误报")
html2 = '<script>var x = { biz: "${window.biz}" }; window.biz = "${window.biz}";</script>'
got = seed.extract_biz_from_html(html2)
print("  got:", got)
assert got is None, f"占位符不应被当成 biz，却得到 {got}"

print("=" * 55)
print("TEST 3: valid_biz 校验规则")
assert seed.valid_biz("MzA5MDMwMTIyNQ==") is True
assert seed.valid_biz("${window.biz}") is False
assert seed.valid_biz("${biz}") is False
assert seed.valid_biz("MzA5MD") is False          # 太短
assert seed.valid_biz("hello world!") is False     # 含空格/感叹号
print("  PASS")

print("=" * 55)
print("TEST 4: URL 参数中的 biz 正常解析")
biz, err = seed.extract_biz(f"https://mp.weixin.qq.com/s?__biz={REAL_BIZ}&mid=1&sn=x")
print("  got:", biz, "err:", err)
assert biz == REAL_BIZ and err is None

print("=" * 55)
print("TEST 5: URL 参数是占位符 → 拒绝")
biz, err = seed.extract_biz("https://mp.weixin.qq.com/s?__biz=%24%7Bwindow.biz%7D&mid=1")
print("  got:", biz, "err:", err)
assert biz is None and err is not None

print("\nALL SEED TESTS PASSED ✓")

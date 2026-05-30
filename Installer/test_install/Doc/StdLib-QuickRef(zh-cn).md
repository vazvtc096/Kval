# Kval 标准库函数速查（zh-cn）

> 函数级速查，按模块分组；每个函数一行用途说明。

## `algo.kval`

- `countDigits(int n)`: 统计十进制位数（`0` 返回 `1`）。
- `sumDigits(int n)`: 统计十进制各位和（按绝对值）。
- `reverseInt(int n)`: 反转十进制数字并保留符号。
- `isPalindromeInt(int n)`: 判断整数是否为回文数。
- `nextPowerOf2(int n)`: 返回不小于 `n` 的最小 2 次幂。
- `prevPowerOf2(int n)`: 返回不大于 `n` 的最大 2 次幂。

## `array.kval`

- `arrayLenInt(array a)`: 统计数组长度。
- `arraySumInt(array a)`: 求数组元素和。
- `arrayMinInt(array a)`: 求数组最小值（空数组返回 `0` 风格）。
- `arrayMaxInt(array a)`: 求数组最大值（空数组返回 `0` 风格）。
- `arrayContainsInt(array a, int x)`: 判断是否包含元素。
- `arrayCountInt(array a, int x)`: 统计元素出现次数。
- `arrayFirstIndexInt(array a, int x)`: 返回首个命中下标，未命中返回 `-1`。

## `bitwise.kval`

- `shl(int a, int n)`: 左移（算术近似：乘 `2^n`）。
- `shr(int a, int n)`: 右移（算术近似：除 `2^n`）。
- `hasBit(int value, int bitIndex)`: 判断某 bit 是否为 1。
- `setBit(int value, int bitIndex)`: 将某 bit 设为 1。
- `clearBit(int value, int bitIndex)`: 将某 bit 清零。
- `toggleBit(int value, int bitIndex)`: 翻转某 bit。
- `bitAnd(int a, int b)`: 位与（非负整数子集）。
- `bitOr(int a, int b)`: 位或（非负整数子集）。
- `bitXor(int a, int b)`: 位异或（非负整数子集）。
- `bitNot(int a)`: 位取反（非负整数子集，按固定宽度近似）。

## `bool.kval`

- `not(bool v)`: 逻辑非。
- `and(bool a, bool b)`: 逻辑与。
- `or(bool a, bool b)`: 逻辑或。
- `xor(bool a, bool b)`: 逻辑异或。
- `boolCount2(bool a, bool b)`: 两个布尔值中真值数量。
- `boolCount3(bool a, bool b, bool c)`: 三个布尔值中真值数量。
- `all2(bool a, bool b)`: 两值是否全为真。
- `any2(bool a, bool b)`: 两值是否至少一真。

## `char.kval`

- `isDigitChar(string c)`: 是否数字字符。
- `isLowerChar(string c)`: 是否小写字母。
- `isUpperChar(string c)`: 是否大写字母。
- `isLetterChar(string c)`: 是否字母。
- `isAlphaNumChar(string c)`: 是否字母或数字。
- `isUnderscoreChar(string c)`: 是否下划线。
- `isIdentifierStartChar(string c)`: 是否可作为标识符首字符。
- `isIdentifierChar(string c)`: 是否可作为标识符字符。
- `isSpaceChar(string c)`: 是否空白字符（空格、制表、换行、回车）。

## `compare.kval`

- `cmpInt(int a, int b)`: 整数三路比较（-1/0/1）。
- `cmpString(string a, string b)`: 字符串三路比较（-1/0/1）。
- `inRangeInclusive(int x, int lo, int hi)`: 闭区间判断。
- `inRangeExclusive(int x, int lo, int hi)`: 开区间判断。
- `chooseBySign(int x, int whenNeg, int whenZero, int whenPos)`: 按符号返回分支值。

## `constants.kval`

- `INT_MAX`: 32 位整型最大值。
- `BYTE_MIN` / `BYTE_MAX`: 字节范围常量。
- `BOOL_FALSE` / `BOOL_TRUE`: 布尔整数常量。
- `EMPTY` / `NEWLINE` / `TAB`: 常见字符串常量。
- `intMinValue()`: 返回 32 位整型最小值。

## `datetime_like.kval`

- `twoDigits(int n)`: 两位零填充。
- `fourDigits(int n)`: 四位零填充。
- `formatDate(int y, int m, int d)`: 格式化日期 `YYYY-MM-DD`。
- `formatTime(int h, int m, int s)`: 格式化时间 `HH:MM:SS`。
- `formatDateTime(...)`: 组合日期时间。
- `isLeapYear(int year)`: 闰年判断。
- `daysInMonth(int year, int month)`: 指定年月天数。

## `encoding.kval`

- `hexDigitLower(int n)`: 0-15 转小写十六进制字符。
- `hexValue(string c)`: 十六进制字符转数值。
- `intToHex(int n)`: 整数转十六进制字符串。
- `hexToInt(string s)`: 十六进制字符串转整数。
- `intToBin(int n)`: 整数转二进制字符串。
- `binToInt(string s)`: 二进制字符串转整数。

## `error.kval`

- `ERR_OK` / `ERR_INVALID_ARG` / `ERR_OUT_OF_RANGE` / `ERR_PARSE` / `ERR_NOT_FOUND` / `ERR_INTERNAL`: 标准错误码。
- `isOk(int err)`: 是否成功码。
- `errorName(int err)`: 错误码转名称。
- `require(bool cond, int errCode)`: 条件检查，不满足返回错误码。

## `hash.kval`

- `hashString(string s)`: 字符串哈希（轻量分类哈希）。
- `hashPairInt(int a, int b)`: 两整数组合哈希。
- `checksumDigits(string s)`: 统计字符串中数字字符和。

## `io.kval`

- `printInt(int n)`: 输出整数。
- `printBool(bool b)`: 输出布尔（`true/false`）。
- `printLine(string s)`: 输出字符串。
- `printPairInt(int a, int b)`: 输出整数对。
- `printLabelInt(string label, int n)`: 标签+整数输出。
- `printLabelBool(string label, bool b)`: 标签+布尔输出。

## `math.kval`

- `abs(int n)`: 绝对值。
- `sgn(int n)`: 符号函数（-1/0/1）。
- `max(int a, int b)`: 最大值。
- `min(int a, int b)`: 最小值。
- `pow(int x, int exp)`: 整数幂（快速幂，负指数返回 `0`）。
- `clamp(int n, int lo, int hi)`: 区间裁剪。
- `gcd(int a, int b)`: 最大公约数。
- `lcm(int a, int b)`: 最小公倍数。
- `isEven(int n)`: 偶数判断。
- `isOdd(int n)`: 奇数判断。
- `square(int n)`: 平方。
- `cube(int n)`: 立方。
- `factorial(int n)`: 阶乘（负数返回 `0`）。

## `numeric.kval`

- `mod(int a, int b)`: 取模（除数 0 返回 0）。
- `floorDiv(int a, int b)`: 向下整除。
- `ceilDiv(int a, int b)`: 向上整除。
- `average2(int a, int b)`: 两数平均（整型）。
- `average3(int a, int b, int c)`: 三数平均（整型）。
- `distance(int a, int b)`: 数轴距离。
- `signStep(int x)`: 返回 -1/0/1。

## `path.kval`

- `normalizeSlashes(string p)`: 路径分隔符归一化（当前实现为透传）。
- `basenameSimple(string p)`: 取文件名部分。
- `dirnameSimple(string p)`: 取目录部分。
- `joinPath2(string a, string b)`: 拼接两段路径。
- `extnameSimple(string p)`: 取扩展名（不含点）。

## `random.kval`

- `srand(int seed)`: 设置随机种子。
- `rand()`: 生成伪随机整数。
- `randRange(int lo, int hi)`: 生成区间随机整数（含端点）。
- `randBool()`: 生成随机布尔值。

## `range.kval`

- `betweenInclusive(int x, int lo, int hi)`: 闭区间判断。
- `betweenExclusive(int x, int lo, int hi)`: 开区间判断。
- `clamp01(int x)`: 裁剪到 `[0, 1]`。
- `clampByte(int x)`: 裁剪到 `[0, 255]`。
- `wrapToRange(int x, int lo, int hi)`: 环绕到区间内。

## `security_like.kval`

- `hasLower(string s)`: 是否含小写字母。
- `hasUpper(string s)`: 是否含大写字母。
- `hasDigit(string s)`: 是否含数字。
- `hasSpecial(string s)`: 是否含特殊字符。
- `passwordStrengthScore(string s)`: 密码强度评分。
- `isStrongPassword(string s)`: 是否强密码。
- `maskMiddle(string s, int keepLeft, int keepRight)`: 中间脱敏。
- `maskEmailSimple(string email)`: 邮箱用户部分脱敏。

## `sort.kval`

- `isSortedAscInt(array a)`: 是否升序。
- `isSortedDescInt(array a)`: 是否降序。

## `stats.kval`

- `sum2(int a, int b)`: 两数和。
- `sum3(int a, int b, int c)`: 三数和。
- `mean2(int a, int b)`: 两数均值（整型）。
- `mean3(int a, int b, int c)`: 三数均值（整型）。
- `range2(int a, int b)`: 两数差距。
- `median3(int a, int b, int c)`: 三数中位数。
- `manhattan2D(int x1, int y1, int x2, int y2)`: 二维曼哈顿距离。

## `string.kval`

- `toInt`: `stringToInt` 别名。
- `fromInt`: `intToString` 别名。
- `repeat(string s, int n)`: 重复字符串。
- `reverse(string s)`: 反转字符串。
- `startsWithChar(string s, string ch)`: 首字符判断。
- `endsWithChar(string s, string ch)`: 末字符判断。
- `countChar(string s, string ch)`: 字符计数。
- `padLeftChar(string s, int width, string ch)`: 左填充。
- `padRightChar(string s, int width, string ch)`: 右填充。

## `string_ext.kval`

- `length(string s)`: 字符串长度。
- `trimLeftSpaces(string s)`: 去左侧空格。
- `trimRightSpaces(string s)`: 去右侧空格。
- `trimSpaces(string s)`: 去两侧空格。
- `startsWith(string s, string prefix)`: 前缀判断。
- `endsWith(string s, string suffix)`: 后缀判断。
- `removeAllChar(string s, string ch)`: 移除指定字符。
- `keepOnlyIdentifierChars(string s)`: 仅保留标识符字符。

## `text_case.kval`

- `toLowerChar(string c)`: 单字符转小写。
- `toUpperChar(string c)`: 单字符转大写。
- `toLower(string s)`: 字符串转小写。
- `toUpper(string s)`: 字符串转大写。
- `equalsIgnoreCase(string a, string b)`: 忽略大小写比较。

## `typecast.kval`

- `stringToInt(string s)`: 字符串转整数（支持前导正负号）。
- `intToString(int n)`: 整数转字符串。
- `intToBool(int n)`: 非零即真。
- `boolToInt(bool b)`: 布尔转 0/1。
- `stringToBool(string s)`: `"true"`/`"1"` 为真。
- `boolToString(bool b)`: 布尔转 `"true"` 或 `"false"`。

## `uuid_like.kval`

- `randomHex(int n)`: 生成 n 位随机十六进制串。
- `uuidLike()`: 生成 UUID-like 字符串。
- `shortId()`: 生成短随机 ID。

## `validate.kval`

- `isIntLiteral(string s)`: 是否整数字面量。
- `isIdentifier(string s)`: 是否合法标识符。
- `isBlank(string s)`: 是否全空白。

# Kval 标准库（zh-cn）

本文档概述 `Kval/Lib/` 当前标准库模块（共 27 个）。  
推荐通过：

```kval
#include "core.kval"
```

一次性引入全部标准库能力。

## 数学与数值

- `math.kval`：`abs` `sgn` `max` `min` `pow` `clamp` `gcd` `lcm` `isEven` `isOdd` `square` `cube` `factorial`
- `numeric.kval`：`mod` `floorDiv` `ceilDiv` `average2` `average3` `distance` `signStep`
- `range.kval`：`betweenInclusive` `betweenExclusive` `clamp01` `clampByte` `wrapToRange`
- `stats.kval`：`sum2` `sum3` `mean2` `mean3` `range2` `median3` `manhattan2D`
- `algo.kval`：`countDigits` `sumDigits` `reverseInt` `isPalindromeInt` `nextPowerOf2` `prevPowerOf2`

## 类型转换与布尔

- `typecast.kval`：`stringToInt` `intToString` `intToBool` `boolToInt` `stringToBool` `boolToString`
- `bool.kval`：`not` `and` `or` `xor` `boolCount2` `boolCount3` `all2` `any2`

## 字符与字符串

- `char.kval`：`isDigitChar` `isLowerChar` `isUpperChar` `isLetterChar` `isAlphaNumChar` `isUnderscoreChar` `isIdentifierStartChar` `isIdentifierChar` `isSpaceChar`
- `string.kval`：`toInt` `fromInt` `repeat` `reverse` `startsWithChar` `endsWithChar` `countChar` `padLeftChar` `padRightChar`
- `string_ext.kval`：`length` `trimLeftSpaces` `trimRightSpaces` `trimSpaces` `startsWith` `endsWith` `removeAllChar` `keepOnlyIdentifierChars`
- `text_case.kval`：`toLowerChar` `toUpperChar` `toLower` `toUpper` `equalsIgnoreCase`

## 校验、比较、错误处理

- `validate.kval`：`isIntLiteral` `isIdentifier` `isBlank`
- `compare.kval`：`cmpInt` `cmpString` `inRangeInclusive` `inRangeExclusive` `chooseBySign`
- `error.kval`：`ERR_OK` `ERR_INVALID_ARG` `ERR_OUT_OF_RANGE` `ERR_PARSE` `ERR_NOT_FOUND` `ERR_INTERNAL` `isOk` `errorName` `require`

## 位运算、随机、哈希、编码

- `bitwise.kval`：`bitAnd` `bitOr` `bitXor` `bitNot` `shl` `shr` `hasBit` `setBit` `clearBit` `toggleBit`
- `random.kval`：`srand` `rand` `randRange` `randBool`
- `hash.kval`：`hashString` `hashPairInt` `checksumDigits`
- `encoding.kval`：`hexDigitLower` `hexValue` `intToHex` `hexToInt` `intToBin` `binToInt`

## 容器、排序、路径、ID、时间

- `array.kval`：`arrayLenInt` `arraySumInt` `arrayMinInt` `arrayMaxInt` `arrayContainsInt` `arrayCountInt` `arrayFirstIndexInt`
- `sort.kval`：`isSortedAscInt` `isSortedDescInt`
- `path.kval`：`normalizeSlashes` `basenameSimple` `dirnameSimple` `joinPath2` `extnameSimple`
- `uuid_like.kval`：`randomHex` `uuidLike` `shortId`
- `datetime_like.kval`：`twoDigits` `fourDigits` `formatDate` `formatTime` `formatDateTime` `isLeapYear` `daysInMonth`

## 安全与输出

- `security_like.kval`：`hasLower` `hasUpper` `hasDigit` `hasSpecial` `passwordStrengthScore` `isStrongPassword` `maskMiddle` `maskEmailSimple`
- `io.kval`：`printInt` `printBool` `printLine` `printPairInt` `printLabelInt` `printLabelBool`

## 常量与聚合

- `constants.kval`：`INT_MAX` `BYTE_MIN` `BYTE_MAX` `BOOL_FALSE` `BOOL_TRUE` `EMPTY` `NEWLINE` `TAB` `intMinValue`
- `core.kval`：聚合入口，统一 `#include`

## 示例

```kval
#include "core.kval"

int main() {
    printLabelInt("gcd", gcd(84, 18));
    print(formatDateTime(2026, 4, 25, 16, 34, 0));
    print(uuidLike());
    print(boolToString(isStrongPassword("Abc123!@#")));
    return 0;
}
```

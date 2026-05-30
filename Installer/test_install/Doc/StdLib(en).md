# Kval Standard Library (en)

This document summarizes the current modules in `Kval/Lib/` (27 files).  
Recommended import:

```kval
#include "core.kval"
```

to load the full standard library surface.

## Math and Numeric

- `math.kval`: `abs` `sgn` `max` `min` `pow` `clamp` `gcd` `lcm` `isEven` `isOdd` `square` `cube` `factorial`
- `numeric.kval`: `mod` `floorDiv` `ceilDiv` `average2` `average3` `distance` `signStep`
- `range.kval`: `betweenInclusive` `betweenExclusive` `clamp01` `clampByte` `wrapToRange`
- `stats.kval`: `sum2` `sum3` `mean2` `mean3` `range2` `median3` `manhattan2D`
- `algo.kval`: `countDigits` `sumDigits` `reverseInt` `isPalindromeInt` `nextPowerOf2` `prevPowerOf2`

## Type Casting and Boolean

- `typecast.kval`: `stringToInt` `intToString` `intToBool` `boolToInt` `stringToBool` `boolToString`
- `bool.kval`: `not` `and` `or` `xor` `boolCount2` `boolCount3` `all2` `any2`

## Char and String

- `char.kval`: `isDigitChar` `isLowerChar` `isUpperChar` `isLetterChar` `isAlphaNumChar` `isUnderscoreChar` `isIdentifierStartChar` `isIdentifierChar` `isSpaceChar`
- `string.kval`: `toInt` `fromInt` `repeat` `reverse` `startsWithChar` `endsWithChar` `countChar` `padLeftChar` `padRightChar`
- `string_ext.kval`: `length` `trimLeftSpaces` `trimRightSpaces` `trimSpaces` `startsWith` `endsWith` `removeAllChar` `keepOnlyIdentifierChars`
- `text_case.kval`: `toLowerChar` `toUpperChar` `toLower` `toUpper` `equalsIgnoreCase`

## Validation, Compare, Error Handling

- `validate.kval`: `isIntLiteral` `isIdentifier` `isBlank`
- `compare.kval`: `cmpInt` `cmpString` `inRangeInclusive` `inRangeExclusive` `chooseBySign`
- `error.kval`: `ERR_OK` `ERR_INVALID_ARG` `ERR_OUT_OF_RANGE` `ERR_PARSE` `ERR_NOT_FOUND` `ERR_INTERNAL` `isOk` `errorName` `require`

## Bitwise, Random, Hash, Encoding

- `bitwise.kval`: `bitAnd` `bitOr` `bitXor` `bitNot` `shl` `shr` `hasBit` `setBit` `clearBit` `toggleBit`
- `random.kval`: `srand` `rand` `randRange` `randBool`
- `hash.kval`: `hashString` `hashPairInt` `checksumDigits`
- `encoding.kval`: `hexDigitLower` `hexValue` `intToHex` `hexToInt` `intToBin` `binToInt`

## Array, Sort, Path, IDs, Date-Time

- `array.kval`: `arrayLenInt` `arraySumInt` `arrayMinInt` `arrayMaxInt` `arrayContainsInt` `arrayCountInt` `arrayFirstIndexInt`
- `sort.kval`: `isSortedAscInt` `isSortedDescInt`
- `path.kval`: `normalizeSlashes` `basenameSimple` `dirnameSimple` `joinPath2` `extnameSimple`
- `uuid_like.kval`: `randomHex` `uuidLike` `shortId`
- `datetime_like.kval`: `twoDigits` `fourDigits` `formatDate` `formatTime` `formatDateTime` `isLeapYear` `daysInMonth`

## Security and Output

- `security_like.kval`: `hasLower` `hasUpper` `hasDigit` `hasSpecial` `passwordStrengthScore` `isStrongPassword` `maskMiddle` `maskEmailSimple`
- `io.kval`: `printInt` `printBool` `printLine` `printPairInt` `printLabelInt` `printLabelBool`

## Constants and Aggregation

- `constants.kval`: `INT_MAX` `BYTE_MIN` `BYTE_MAX` `BOOL_FALSE` `BOOL_TRUE` `EMPTY` `NEWLINE` `TAB` `intMinValue`
- `core.kval`: aggregate entrypoint for one-shot include

## Example

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

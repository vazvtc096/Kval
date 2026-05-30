# Kval Stdlib Quick Reference (en)

> Function-level quick reference. One-line purpose per function, grouped by module.

## `algo.kval`

- `countDigits(int n)`: Decimal digit count (`0` returns `1`).
- `sumDigits(int n)`: Sum of decimal digits (absolute value).
- `reverseInt(int n)`: Reverse decimal digits while keeping sign.
- `isPalindromeInt(int n)`: Integer palindrome check.
- `nextPowerOf2(int n)`: Smallest power-of-two not less than `n`.
- `prevPowerOf2(int n)`: Largest power-of-two not greater than `n`.

## `array.kval`

- `arrayLenInt(array a)`: Array length.
- `arraySumInt(array a)`: Sum of elements.
- `arrayMinInt(array a)`: Minimum element (empty-array style fallback `0`).
- `arrayMaxInt(array a)`: Maximum element (empty-array style fallback `0`).
- `arrayContainsInt(array a, int x)`: Membership test.
- `arrayCountInt(array a, int x)`: Count occurrences.
- `arrayFirstIndexInt(array a, int x)`: First index, or `-1` if missing.

## `bitwise.kval`

- `shl(int a, int n)`: Shift-left approximation via `a * 2^n`.
- `shr(int a, int n)`: Shift-right approximation via `a / 2^n`.
- `hasBit(int value, int bitIndex)`: Test bit.
- `setBit(int value, int bitIndex)`: Set bit to 1.
- `clearBit(int value, int bitIndex)`: Clear bit to 0.
- `toggleBit(int value, int bitIndex)`: Flip bit.
- `bitAnd(int a, int b)`: Bitwise AND (non-negative subset).
- `bitOr(int a, int b)`: Bitwise OR (non-negative subset).
- `bitXor(int a, int b)`: Bitwise XOR (non-negative subset).
- `bitNot(int a)`: Bitwise NOT approximation over fixed width.

## `bool.kval`

- `not(bool v)`: Logical NOT.
- `and(bool a, bool b)`: Logical AND.
- `or(bool a, bool b)`: Logical OR.
- `xor(bool a, bool b)`: Logical XOR.
- `boolCount2(bool a, bool b)`: Number of true values among 2 args.
- `boolCount3(bool a, bool b, bool c)`: Number of true values among 3 args.
- `all2(bool a, bool b)`: Both true.
- `any2(bool a, bool b)`: At least one true.

## `char.kval`

- `isDigitChar(string c)`: Digit test.
- `isLowerChar(string c)`: Lowercase letter test.
- `isUpperChar(string c)`: Uppercase letter test.
- `isLetterChar(string c)`: Letter test.
- `isAlphaNumChar(string c)`: Alphanumeric test.
- `isUnderscoreChar(string c)`: Underscore test.
- `isIdentifierStartChar(string c)`: Valid identifier-start char.
- `isIdentifierChar(string c)`: Valid identifier char.
- `isSpaceChar(string c)`: Whitespace test.

## `compare.kval`

- `cmpInt(int a, int b)`: Three-way integer comparison (-1/0/1).
- `cmpString(string a, string b)`: Three-way string comparison (-1/0/1).
- `inRangeInclusive(int x, int lo, int hi)`: Inclusive range check.
- `inRangeExclusive(int x, int lo, int hi)`: Exclusive range check.
- `chooseBySign(int x, int whenNeg, int whenZero, int whenPos)`: Sign-based branch value.

## `constants.kval`

- `INT_MAX`: 32-bit signed integer max.
- `BYTE_MIN` / `BYTE_MAX`: Byte boundaries.
- `BOOL_FALSE` / `BOOL_TRUE`: Boolean integer constants.
- `EMPTY` / `NEWLINE` / `TAB`: Common string constants.
- `intMinValue()`: 32-bit signed integer min.

## `datetime_like.kval`

- `twoDigits(int n)`: Zero-pad to two digits.
- `fourDigits(int n)`: Zero-pad to four digits.
- `formatDate(int y, int m, int d)`: `YYYY-MM-DD`.
- `formatTime(int h, int m, int s)`: `HH:MM:SS`.
- `formatDateTime(...)`: Combined date-time format.
- `isLeapYear(int year)`: Leap-year check.
- `daysInMonth(int year, int month)`: Days in given month.

## `encoding.kval`

- `hexDigitLower(int n)`: 0-15 to lowercase hex digit.
- `hexValue(string c)`: Hex digit to integer value.
- `intToHex(int n)`: Integer to hex string.
- `hexToInt(string s)`: Hex string to integer.
- `intToBin(int n)`: Integer to binary string.
- `binToInt(string s)`: Binary string to integer.

## `error.kval`

- `ERR_OK` / `ERR_INVALID_ARG` / `ERR_OUT_OF_RANGE` / `ERR_PARSE` / `ERR_NOT_FOUND` / `ERR_INTERNAL`: Standard error codes.
- `isOk(int err)`: Success-code check.
- `errorName(int err)`: Error code name lookup.
- `require(bool cond, int errCode)`: Condition guard returning error code on failure.

## `hash.kval`

- `hashString(string s)`: Lightweight string hash.
- `hashPairInt(int a, int b)`: Pair hash for two integers.
- `checksumDigits(string s)`: Sum of all digit chars in string.

## `io.kval`

- `printInt(int n)`: Print integer.
- `printBool(bool b)`: Print boolean as `true/false`.
- `printLine(string s)`: Print string.
- `printPairInt(int a, int b)`: Print integer pair.
- `printLabelInt(string label, int n)`: Labeled integer print.
- `printLabelBool(string label, bool b)`: Labeled boolean print.

## `math.kval`

- `abs(int n)`: Absolute value.
- `sgn(int n)`: Sign function (-1/0/1).
- `max(int a, int b)`: Maximum.
- `min(int a, int b)`: Minimum.
- `pow(int x, int exp)`: Integer exponentiation (fast pow; negative exp => `0`).
- `clamp(int n, int lo, int hi)`: Range clamp.
- `gcd(int a, int b)`: Greatest common divisor.
- `lcm(int a, int b)`: Least common multiple.
- `isEven(int n)`: Even check.
- `isOdd(int n)`: Odd check.
- `square(int n)`: Square.
- `cube(int n)`: Cube.
- `factorial(int n)`: Factorial (negative => `0`).

## `numeric.kval`

- `mod(int a, int b)`: Modulo (`b == 0` => `0`).
- `floorDiv(int a, int b)`: Floor division.
- `ceilDiv(int a, int b)`: Ceil division.
- `average2(int a, int b)`: Integer mean of two values.
- `average3(int a, int b, int c)`: Integer mean of three values.
- `distance(int a, int b)`: Absolute distance.
- `signStep(int x)`: Returns -1/0/1.

## `path.kval`

- `normalizeSlashes(string p)`: Normalize separators (currently passthrough).
- `basenameSimple(string p)`: Basename extraction.
- `dirnameSimple(string p)`: Dirname extraction.
- `joinPath2(string a, string b)`: Join two path segments.
- `extnameSimple(string p)`: Extension name without dot.

## `random.kval`

- `srand(int seed)`: Seed random state.
- `rand()`: Pseudo-random integer.
- `randRange(int lo, int hi)`: Inclusive random integer in range.
- `randBool()`: Random boolean.

## `range.kval`

- `betweenInclusive(int x, int lo, int hi)`: Inclusive range check.
- `betweenExclusive(int x, int lo, int hi)`: Exclusive range check.
- `clamp01(int x)`: Clamp to `[0, 1]`.
- `clampByte(int x)`: Clamp to `[0, 255]`.
- `wrapToRange(int x, int lo, int hi)`: Wrap value into range.

## `security_like.kval`

- `hasLower(string s)`: Contains lowercase letter.
- `hasUpper(string s)`: Contains uppercase letter.
- `hasDigit(string s)`: Contains digit.
- `hasSpecial(string s)`: Contains special char.
- `passwordStrengthScore(string s)`: Password strength score.
- `isStrongPassword(string s)`: Strong-password predicate.
- `maskMiddle(string s, int keepLeft, int keepRight)`: Mask middle characters.
- `maskEmailSimple(string email)`: Mask email user-part.

## `sort.kval`

- `isSortedAscInt(array a)`: Ascending order check.
- `isSortedDescInt(array a)`: Descending order check.

## `stats.kval`

- `sum2(int a, int b)`: Sum of two integers.
- `sum3(int a, int b, int c)`: Sum of three integers.
- `mean2(int a, int b)`: Integer mean of two values.
- `mean3(int a, int b, int c)`: Integer mean of three values.
- `range2(int a, int b)`: Distance between two values.
- `median3(int a, int b, int c)`: Median of three integers.
- `manhattan2D(int x1, int y1, int x2, int y2)`: 2D Manhattan distance.

## `string.kval`

- `toInt`: Alias of `stringToInt`.
- `fromInt`: Alias of `intToString`.
- `repeat(string s, int n)`: Repeat string.
- `reverse(string s)`: Reverse string.
- `startsWithChar(string s, string ch)`: First-char check.
- `endsWithChar(string s, string ch)`: Last-char check.
- `countChar(string s, string ch)`: Character frequency.
- `padLeftChar(string s, int width, string ch)`: Left pad.
- `padRightChar(string s, int width, string ch)`: Right pad.

## `string_ext.kval`

- `length(string s)`: String length.
- `trimLeftSpaces(string s)`: Trim left spaces.
- `trimRightSpaces(string s)`: Trim right spaces.
- `trimSpaces(string s)`: Trim both sides.
- `startsWith(string s, string prefix)`: Prefix check.
- `endsWith(string s, string suffix)`: Suffix check.
- `removeAllChar(string s, string ch)`: Remove all matching chars.
- `keepOnlyIdentifierChars(string s)`: Keep only identifier chars.

## `text_case.kval`

- `toLowerChar(string c)`: Single-char lowercase.
- `toUpperChar(string c)`: Single-char uppercase.
- `toLower(string s)`: Lowercase string.
- `toUpper(string s)`: Uppercase string.
- `equalsIgnoreCase(string a, string b)`: Case-insensitive equality.

## `typecast.kval`

- `stringToInt(string s)`: String to integer (supports optional sign).
- `intToString(int n)`: Integer to string.
- `intToBool(int n)`: Non-zero => true.
- `boolToInt(bool b)`: Boolean to 0/1.
- `stringToBool(string s)`: `"true"`/`"1"` => true.
- `boolToString(bool b)`: Boolean to `"true"`/`"false"`.

## `uuid_like.kval`

- `randomHex(int n)`: Random hex string with length `n`.
- `uuidLike()`: UUID-like random identifier.
- `shortId()`: Short random ID.

## `validate.kval`

- `isIntLiteral(string s)`: Integer-literal validation.
- `isIdentifier(string s)`: Identifier validation.
- `isBlank(string s)`: Whitespace-only check.

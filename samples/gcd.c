/* Sample original: Euclid's algorithm, the way a textbook writes it. */
#include <stdio.h>

long gcd(long a, long b) {
    while (b != 0) {
        long t = a % b;
        a = b;
        b = t;
    }
    return a;
}

long lcm(long a, long b) {
    return a / gcd(a, b) * b;
}

int main(void) {
    printf("%ld %ld\n", gcd(48, 18), lcm(4, 6));
    return 0;
}

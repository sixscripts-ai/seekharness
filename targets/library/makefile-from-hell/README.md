# Makefile From Hell

Repair the Makefile. Required behavior:

- `make` builds `build/calc`.
- `./build/calc 7 5` prints `sum=12 product=35`.
- `make test` runs the project smoke test.
- Object files rebuild when `include/mathx.h` changes.

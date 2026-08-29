CC=gcc
CFLAGS=-O2

all: calc

calc: main.o math.o
	$(CC) main.o math.o -o calc

main.o: src/main.c
	$(CC) $(CFLAGS) -c src/main.c -o main.o

math.o: src/mathx.c
	$(CC) $(CFLAGS) -c src/mathx.c -o math.o

test:
	./tests/smoke.sh

clean:
	rm -f *.o calc

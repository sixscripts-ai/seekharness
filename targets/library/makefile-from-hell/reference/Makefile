CC ?= gcc
CPPFLAGS := -Iinclude
CFLAGS ?= -O2 -Wall -Wextra -MMD -MP
BUILD := build
OBJS := $(BUILD)/main.o $(BUILD)/mathx.o
DEPS := $(OBJS:.o=.d)

.PHONY: all clean test
all: $(BUILD)/calc

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/calc: $(OBJS)
	$(CC) $(OBJS) -o $@

$(BUILD)/main.o: src/main.c | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

$(BUILD)/mathx.o: src/mathx.c | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

test: $(BUILD)/calc
	./tests/smoke.sh

clean:
	rm -rf $(BUILD)

-include $(DEPS)

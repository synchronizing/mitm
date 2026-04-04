CC = clang
ARCHS = -arch arm64 -arch x86_64
CFLAGS = -dynamiclib -fPIC $(ARCHS) -Wall -O2
TARGET = ../lib/libmitmhook.dylib

$(TARGET): hook.c
	mkdir -p ../lib
	$(CC) $(CFLAGS) -o $(TARGET) hook.c

clean:
	rm -f $(TARGET)

.PHONY: clean

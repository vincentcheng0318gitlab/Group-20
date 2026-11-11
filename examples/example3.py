def functin():
    a,b = 1,1
    while True:
        yield a
        a,b=b,a+b
generote = functin()
print([next(generote) for _ in range(10)])

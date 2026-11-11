def functin():
    a,b = 1,1
    while True:
        yield a
        a,b=b,a+b
generote = functin()
print([str(next(generote))+" ,NEXT NUMBAR" for _ in range(int(input())])

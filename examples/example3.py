'''Spellings of variables can be checked as well. Yet, intent strings in the code are not detected'''
def fibonnaci():
    a,b = 1,1
    while True:
        yield a
        a,b=b,a+b
generote = fibonnaci()
print("fibonnaci numbers -- type a nymber as input")
print([str(next(generote)) for _ in range(int(input()))])
 

'''Check mispelling in functions (even considered words that contains hyphens and dashes)'''
def remov_daplicetes(s):
    t = ''
    for i in s:
        if i not in t:
            t += i
    return t

import os
import sys
import json
import random
from datetime import datetime
from os import path
import math


CONSTANT_value = 100  
myVariable = "hello"  
_privateVar = 42      

def badFunction(x,y,z):  
    result=x+y*z  
    if result>10:  
        print("result is big")  
        return True
    else:  
        return False

def too_many_arguments(a,b,c,d,e,f,g,h,i,j):  
    return a+b+c+d+e+f+g+h+i+j

def empty_function():
    pass

class myClass:
    def __init__(self,Name,Age):  
        self.Name = Name  
        self.Age = Age    
        
    def GetData(self):  
        return self.Name

def long_line_function():
        very_long_variable_name_that_is_unnecessarily_long = "This is a very long string that exceeds the recommended line length limit for Python code and should be broken up"
    return very_long_variable_name_that_is_unnecessarily_long
    
def trailing_whitespace():
    return "has trailing spaces"    
x=1; y=2; z=3

try:
    result = 10 / 0
except: 
    print("error")

flag = True
if flag == True:
    print("flag is true")

value = None
if value == None:  
    print("value is none")

unused_var = 42  

def bad_default(items=[]):      items.append(1)
    return items

my_list = [1,2,3,4,5]
for i in range(len(my_list)):  # Bad: Should use enumerate
    print(my_list[i])

print("done")    

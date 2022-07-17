from django.shortcuts import render

# Create your views here.

from django.shortcuts import render, HttpResponse


async def index(request):
    return render(request, 'index.html')


async def engagement(request):
    return HttpResponse(request.POST['test'])






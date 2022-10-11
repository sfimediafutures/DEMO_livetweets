from django.shortcuts import render, HttpResponse

# Create your views here.


async def index(request):

    return render(request, 'index.html')


async def dashboard(request):
    return render(request, 'dashboard.html')


async def engagement(request):
    return HttpResponse(request.POST['test'])






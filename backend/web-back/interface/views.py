from django.shortcuts import render, HttpResponse

# Create your views here.


async def index(request):
    context = {}




    return render(request, 'index.html', context=context)


async def dashboard(request):
    return render(request, 'dashboard.html')

async def dashboard2(request):
    return render(request, 'v2_dashboard.html')


async def engagement(request):
    return HttpResponse(request.POST['test'])






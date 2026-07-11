from django.urls import path

from apps.bids import views

urlpatterns = [
    path('bids', views.list_create_bids),
    path('bids/<int:bid_id>', views.bid_detail),
    path('bids/<int:bid_id>/steps', views.bid_steps),
    path('bids/<int:bid_id>/steps/<int:step_id>', views.update_bid_step),
    path('bids/<int:bid_id>/chapters', views.bid_chapters),
    path('bids/<int:bid_id>/chapters/<int:chapter_id>', views.chapter_detail),
    path('bids/<int:bid_id>/export', views.export_bid),
    path('bid-analyzer/analyze', views.analyze_bid_document),
    path('bid-analyzer/generate-outline', views.generate_outline),
]

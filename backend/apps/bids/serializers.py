from rest_framework import serializers

from apps.bids.models import Bid, BidChapter, BidStep
from apps.users.serializers import UserSerializer


class BidStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidStep
        fields = ['id', 'order', 'label', 'status']


class BidChapterSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = BidChapter
        fields = ['id', 'bid_id', 'parent_id', 'title', 'order', 'content', 'children']

    def get_children(self, obj):
        children = obj.children.all()
        if not children:
            return []
        return BidChapterSerializer(children, many=True).data


class BidChapterCreateSerializer(serializers.Serializer):
    parent_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    title = serializers.CharField(max_length=256)
    order = serializers.IntegerField(default=0)
    content = serializers.JSONField(required=False, allow_null=True, default=None)


class BidChapterUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=256, required=False)
    order = serializers.IntegerField(required=False)
    content = serializers.JSONField(required=False, allow_null=True)


class BidStepUpdateSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=16)


class BidOutlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bid
        fields = ['id', 'title', 'completed_chapters', 'total_chapters', 'status', 'created_at']


class BidDetailSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    chapters = serializers.SerializerMethodField()
    steps = BidStepSerializer(many=True, read_only=True)

    class Meta:
        model = Bid
        fields = ['id', 'title', 'completed_chapters', 'total_chapters', 'status',
                  'created_at', 'user', 'chapters', 'steps']

    def get_chapters(self, obj):
        top_chapters = obj.chapters.filter(parent__isnull=True)
        return BidChapterSerializer(top_chapters, many=True).data


class BidCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=256)
    user_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)


class BidUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=256, required=False)
    status = serializers.CharField(max_length=32, required=False)

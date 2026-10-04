def test_core_imports():
    """Test that core modules can be imported successfully."""
    import youtube_lead_generator.core.config
    import youtube_lead_generator.core.database
    import youtube_lead_generator.core.workspace_manager
    assert True

def test_service_imports():
    """Test that primary services can be imported successfully."""
    from youtube_lead_generator.services.youtube.channel_service import ChannelService
    from youtube_lead_generator.services.extractors.category_extractor import CategoryExtractor
    assert ChannelService is not None
    assert CategoryExtractor is not None

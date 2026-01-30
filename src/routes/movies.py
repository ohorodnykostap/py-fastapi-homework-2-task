from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from database.session_postgresql import get_db
from database.models import (
    MovieModel,
    CountryModel,
    GenreModel,
    ActorModel,
    LanguageModel
)
from schemas.movies import (
    MovieDetailSchema,
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieCreateSchema,
    MovieUpdateSchema,
    CountrySchema,
    GenreSchema,
    ActorSchema,
    LanguageSchema
)

router = APIRouter()


@router.get("/movies/", response_model=MovieListResponseSchema)
async def list_movies(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(10, ge=1, le=20),
        db: AsyncSession = Depends(get_db)
):
    total_items = await db.scalar(select(func.count(MovieModel.id)))
    total_pages = (total_items + per_page - 1) // per_page
    if page > total_pages and total_pages != 0:
        raise HTTPException(status_code=404, detail="No movies found.")

    offset = (page - 1) * per_page
    result = await db.execute(
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    movies = result.scalars().all()
    if not movies:
        raise HTTPException(status_code=404, detail="No movies found.")

    base_url = str(request.url_for("list_movies"))
    prev_page = f"{base_url}?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"{base_url}?page={page + 1}&per_page={per_page}" if page < total_pages else None

    return MovieListResponseSchema(
        movies=[MovieListItemSchema(
            id=m.id,
            name=m.name,
            date=m.date,
            score=m.score,
            overview=m.overview
        ) for m in movies],
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items
    )


@router.post("/movies/", response_model=MovieDetailSchema, status_code=201)
async def create_movie(movie_in: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    country = await db.scalar(select(CountryModel).where(CountryModel.code == movie_in.country))
    if not country:
        country = CountryModel(code=movie_in.country)
        db.add(country)
        await db.commit()
        await db.refresh(country)

    genres = []
    for g in movie_in.genres:
        genre = await db.scalar(select(GenreModel).where(GenreModel.name == g))
        if not genre:
            genre = GenreModel(name=g)
            db.add(genre)
            await db.commit()
            await db.refresh(genre)
        genres.append(genre)

    actors = []
    for a in movie_in.actors:
        actor = await db.scalar(select(ActorModel).where(ActorModel.name == a))
        if not actor:
            actor = ActorModel(name=a)
            db.add(actor)
            await db.commit()
            await db.refresh(actor)
        actors.append(actor)

    languages = []
    for language in movie_in.languages:
        lang = await db.scalar(select(LanguageModel).where(LanguageModel.name == language))
        if not lang:
            lang = LanguageModel(name=language)
            db.add(lang)
            await db.commit()
            await db.refresh(lang)
        languages.append(lang)

    movie = MovieModel(
        name=movie_in.name,
        date=movie_in.date,
        score=movie_in.score,
        overview=movie_in.overview,
        status=movie_in.status,
        budget=movie_in.budget,
        revenue=movie_in.revenue,
        country=country,
        genres=genres,
        actors=actors,
        languages=languages
    )

    db.add(movie)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A movie with the name '{movie_in.name}' and release date '{movie_in.date}' already exists."
        )
    await db.refresh(movie)

    return MovieDetailSchema(
        id=movie.id,
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=movie.status,
        budget=float(movie.budget),
        revenue=movie.revenue,
        country=CountrySchema(
            id=movie.country.id,
            code=movie.country.code,
            name=movie.country.name
        ),
        genres=[GenreSchema(id=g.id, name=g.name) for g in movie.genres],
        actors=[ActorSchema(id=a.id, name=a.name) for a in movie.actors],
        languages=[LanguageSchema(id=lang.id, name=lang.name) for lang in movie.languages]
    )


@router.get("/movies/{movie_id}/", response_model=MovieDetailSchema)
async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages)
        )
        .where(MovieModel.id == movie_id)
    )
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    return MovieDetailSchema(
        id=movie.id,
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=movie.status,
        budget=float(movie.budget),
        revenue=movie.revenue,
        country=CountrySchema(
            id=movie.country.id,
            code=movie.country.code,
            name=movie.country.name
        ),
        genres=[GenreSchema(id=g.id, name=g.name) for g in movie.genres],
        actors=[ActorSchema(id=a.id, name=a.name) for a in movie.actors],
        languages=[LanguageSchema(id=lang.id, name=lang.name) for lang in movie.languages]
    )


@router.delete("/movies/{movie_id}/", status_code=204)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    await db.delete(movie)
    await db.commit()
    return


@router.patch("/movies/{movie_id}/")
async def update_movie(movie_id: int, movie_in: MovieUpdateSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    for field, value in movie_in.dict(exclude_unset=True).items():
        setattr(movie, field, value)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")
    return {"detail": "Movie updated successfully."}

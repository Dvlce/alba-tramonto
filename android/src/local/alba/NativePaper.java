package local.alba;

import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Subtle paper patterns behind native editable text. */
final class NativePaper extends Drawable {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final String paper;private final float density;
    NativePaper(Context context,String paper){this.paper=paper;density=context.getResources().getDisplayMetrics().density;}
    @Override public void draw(Canvas canvas){Rect r=getBounds();paint.setColor(NativeUi.PAPER);canvas.drawRect(r,paint);paint.setColor(0x22798a70);paint.setStrokeWidth(density*.6f);
        float step=(paper.equals("grid")||paper.equals("dots")?20:32)*density;
        if(paper.equals("dots")){for(float y=r.top+step;y<r.bottom;y+=step)for(float x=r.left+step;x<r.right;x+=step)canvas.drawCircle(x,y,density*.7f,paint);}
        else if(!paper.equals("plain")){for(float y=r.top+step;y<r.bottom;y+=step)canvas.drawLine(r.left,y,r.right,y,paint);if(paper.equals("grid")||paper.equals("engineering"))for(float x=r.left+step;x<r.right;x+=step)canvas.drawLine(x,r.top,x,r.bottom,paint);}
    }
    @Override public void getOutline(Outline outline){outline.setRoundRect(getBounds(),20*density);}
    @Override public void setAlpha(int alpha){paint.setAlpha(alpha);}
    @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}
    @Override public int getOpacity(){return PixelFormat.OPAQUE;}
}
